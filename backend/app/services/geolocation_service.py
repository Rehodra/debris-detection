"""
Geolocation and Geodesy Service for MarineScan.
Translates sonar waterfall pixel detections into precision geographic coordinates (WGS84, UTM, DMS),
applies towfish catenary layback corrections, and generates standard GeoJSON features for mapping.
"""

import math
import logging
from typing import Optional, List, Dict, Any, Tuple

from app.schemas.geolocation import (
    NavigationalFix,
    TowfishConfig,
    SonarScanOrigin,
    GeoCoordinates,
    GeolocatedTarget,
    GeoJSONGeometry,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    BatchGeolocationResponse,
)
from app.schemas.detection import BoundingBox, DetectionItem

logger = logging.getLogger("marinescan.services.geolocation")

# WGS84 Ellipsoid Constants
WGS84_A = 6378137.0           # Semi-major axis in meters
WGS84_F = 1.0 / 298.257223563 # Flattening
WGS84_B = WGS84_A * (1.0 - WGS84_F) # Semi-minor axis (~6356752.3142 m)
WGS84_E2 = 2.0 * WGS84_F - (WGS84_F ** 2) # First eccentricity squared (~0.00669437999014)


class GeolocationService:
    """Production geodetic positioning and maritime navigation engine."""

    # -------------------------------------------------------------------------
    # 1. WGS84 Geodetic Projection Engine
    # -------------------------------------------------------------------------

    def wgs84_direct_projection(
        self,
        lat_deg: float,
        lon_deg: float,
        delta_east_m: float,
        delta_north_m: float,
    ) -> Tuple[float, float]:
        """
        Project local East-North metric displacements from a WGS84 origin to new (Lat, Lon).
        Uses meridional and prime-vertical principal radii of curvature.
        """
        phi = math.radians(lat_deg)
        sin_phi = math.sin(phi)
        sin2_phi = sin_phi * sin_phi

        # Meridional radius of curvature (North-South)
        r_m = (WGS84_A * (1.0 - WGS84_E2)) / ((1.0 - WGS84_E2 * sin2_phi) ** 1.5)

        # Prime vertical radius of curvature (East-West)
        r_n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin2_phi)

        # Angular displacements in radians
        d_phi = delta_north_m / r_m
        cos_phi = math.cos(phi)
        d_lambda = delta_east_m / (r_n * cos_phi) if abs(cos_phi) > 1e-9 else 0.0

        target_lat = lat_deg + math.degrees(d_phi)
        target_lon = lon_deg + math.degrees(d_lambda)

        # Wrap longitude to [-180, 180]
        target_lon = (target_lon + 180.0) % 360.0 - 180.0

        return round(target_lat, 7), round(target_lon, 7)

    # -------------------------------------------------------------------------
    # 2. Towfish Layback Correction (Catenary / Slant Cable Model)
    # -------------------------------------------------------------------------

    def calculate_towfish_position(
        self,
        vessel_fix: NavigationalFix,
        towfish_cfg: TowfishConfig,
    ) -> Tuple[GeoCoordinates, float]:
        """
        Calculate the real-world geographic coordinates of the towfish behind the surface vessel.
        Uses cable payout, towfish depth, and catenary curvature factor.
        """
        cable = max(0.0, towfish_cfg.cable_payout_m)
        depth = max(0.0, towfish_cfg.fish_depth_m)

        # Catenary horizontal layback
        slant_layback = math.sqrt(max(0.0, (cable ** 2) - (depth ** 2)))
        true_layback = slant_layback * towfish_cfg.catenary_factor

        # Towfish is trailed astern (reciprocal heading: heading - 180 deg)
        reciprocal_heading_deg = (vessel_fix.heading_degrees + 180.0) % 360.0
        rec_rad = math.radians(reciprocal_heading_deg)

        # Displacement of towfish relative to vessel
        delta_east = true_layback * math.sin(rec_rad)
        delta_north = true_layback * math.cos(rec_rad)

        fish_lat, fish_lon = self.wgs84_direct_projection(
            lat_deg=vessel_fix.latitude,
            lon_deg=vessel_fix.longitude,
            delta_east_m=delta_east,
            delta_north_m=delta_north,
        )

        fish_coords = self.to_geo_coordinates(fish_lat, fish_lon, depth_m=depth)
        return fish_coords, round(true_layback, 2)

    # -------------------------------------------------------------------------
    # 3. Sonar Waterfall Pixel to Track-Frame Offsets
    # -------------------------------------------------------------------------

    def pixel_to_seafloor_offset(
        self,
        pixel_x: float,
        pixel_y: float,
        sonar_origin: SonarScanOrigin,
    ) -> Tuple[float, float]:
        """
        Translate image pixel coordinate into vehicle track-frame metric offsets:
        - Across-track (dx): perpendicular to heading (+ starboard, - port)
        - Along-track (dy): along vehicle heading (+ forward, - astern)
        """
        # Across-track offset: positive = Starboard (right of nadir), negative = Port (left of nadir)
        across_offset_m = (pixel_x - sonar_origin.nadir_pixel_x) * sonar_origin.across_track_gsd_m

        # Along-track offset: scan line index relative to reference fix row
        along_offset_m = (pixel_y - sonar_origin.reference_pixel_y) * sonar_origin.along_track_gsd_m

        return round(across_offset_m, 3), round(along_offset_m, 3)

    # -------------------------------------------------------------------------
    # 4. Navigational Azimuth Heading Rotation & Projection
    # -------------------------------------------------------------------------

    def track_offsets_to_geo(
        self,
        sensor_lat: float,
        sensor_lon: float,
        heading_deg: float,
        across_offset_m: float,
        along_offset_m: float,
        target_depth_m: Optional[float] = None,
    ) -> Tuple[GeoCoordinates, float, float]:
        """
        Rotate track offsets by true gyro heading (0 = North, 90 = East) and project to WGS84.
        Returns:
            Tuple[GeoCoordinates, distance_m, bearing_deg]
        """
        heading_rad = math.radians(heading_deg)
        sin_h = math.sin(heading_rad)
        cos_h = math.cos(heading_rad)

        # Navigational rotation matrix:
        # Forward unit vector: (sin_h, cos_h) for (East, North)
        # Starboard unit vector: (cos_h, -sin_h) for (East, North)
        delta_east = along_offset_m * sin_h + across_offset_m * cos_h
        delta_north = along_offset_m * cos_h - across_offset_m * sin_h

        target_lat, target_lon = self.wgs84_direct_projection(
            lat_deg=sensor_lat,
            lon_deg=sensor_lon,
            delta_east_m=delta_east,
            delta_north_m=delta_north,
        )

        distance = math.hypot(delta_east, delta_north)
        bearing = (math.degrees(math.atan2(delta_east, delta_north)) + 360.0) % 360.0

        coords = self.to_geo_coordinates(target_lat, target_lon, depth_m=target_depth_m)
        return coords, round(distance, 2), round(bearing, 2)

    # -------------------------------------------------------------------------
    # 5. Geodetic Standards: DMS & UTM Conversion
    # -------------------------------------------------------------------------

    def to_dms(self, lat: float, lon: float) -> str:
        """Format decimal degrees into nautical Degrees Minutes Seconds string."""
        lat_hem = "N" if lat >= 0 else "S"
        lon_hem = "E" if lon >= 0 else "W"

        lat_abs = abs(lat)
        lat_d = int(lat_abs)
        lat_m = int((lat_abs - lat_d) * 60.0)
        lat_s = (lat_abs - lat_d - lat_m / 60.0) * 3600.0

        lon_abs = abs(lon)
        lon_d = int(lon_abs)
        lon_m = int((lon_abs - lon_d) * 60.0)
        lon_s = (lon_abs - lon_d - lon_m / 60.0) * 3600.0

        return f"{lat_d:02d}° {lat_m:02d}' {lat_s:04.1f}\" {lat_hem}, {lon_d:03d}° {lon_m:02d}' {lon_s:04.1f}\" {lon_hem}"

    def to_utm(self, lat: float, lon: float) -> Tuple[str, float, float]:
        """
        Convert WGS84 Lat/Lon to Universal Transverse Mercator (UTM) Zone, Easting, Northing.
        """
        zone_num = int((lon + 180.0) / 6.0) + 1
        hemisphere = "N" if lat >= 0 else "S"
        zone_str = f"{zone_num}{hemisphere}"

        # Central meridian
        lon0 = math.radians((zone_num - 1) * 6 - 180 + 3)
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        k0 = 0.9996
        e2 = WGS84_E2
        e_prime2 = e2 / (1.0 - e2)

        sin_lat = math.sin(lat_rad)
        cos_lat = math.cos(lat_rad)
        tan_lat = math.tan(lat_rad)

        n = WGS84_A / math.sqrt(1.0 - e2 * (sin_lat ** 2))
        t = tan_lat ** 2
        c = e_prime2 * (cos_lat ** 2)
        a_val = cos_lat * (lon_rad - lon0)

        # Meridional arc distance
        m = WGS84_A * (
            (1.0 - e2 / 4.0 - 3.0 * (e2 ** 2) / 64.0 - 5.0 * (e2 ** 3) / 256.0) * lat_rad
            - (3.0 * e2 / 8.0 + 3.0 * (e2 ** 2) / 32.0 + 45.0 * (e2 ** 3) / 1024.0) * math.sin(2.0 * lat_rad)
            + (15.0 * (e2 ** 2) / 256.0 + 45.0 * (e2 ** 3) / 1024.0) * math.sin(4.0 * lat_rad)
            - (35.0 * (e2 ** 3) / 3072.0) * math.sin(6.0 * lat_rad)
        )

        easting = k0 * n * (
            a_val
            + (1.0 - t + c) * (a_val ** 3) / 6.0
            + (5.0 - 18.0 * t + (t ** 2) + 72.0 * c - 58.0 * e_prime2) * (a_val ** 5) / 120.0
        ) + 500000.0  # False Easting

        northing = k0 * (
            m
            + n * tan_lat * (
                (a_val ** 2) / 2.0
                + (5.0 - t + 9.0 * c + 4.0 * (c ** 2)) * (a_val ** 4) / 24.0
                + (61.0 - 58.0 * t + (t ** 2) + 600.0 * c - 330.0 * e_prime2) * (a_val ** 6) / 720.0
            )
        )
        if lat < 0:
            northing += 10000000.0  # False Northing for Southern Hemisphere

        return zone_str, round(easting, 2), round(northing, 2)

    def to_geo_coordinates(
        self,
        lat: float,
        lon: float,
        depth_m: Optional[float] = None,
    ) -> GeoCoordinates:
        """Helper to create a complete GeoCoordinates object."""
        dms = self.to_dms(lat, lon)
        zone, easting, northing = self.to_utm(lat, lon)
        return GeoCoordinates(
            latitude=round(lat, 7),
            longitude=round(lon, 7),
            dms_string=dms,
            utm_zone=zone,
            utm_easting_m=easting,
            utm_northing_m=northing,
            depth_m=round(depth_m, 2) if depth_m is not None else None,
        )

    # -------------------------------------------------------------------------
    # 6. Single Target & Batch Geolocation Pipeline
    # -------------------------------------------------------------------------

    def geolocate_target(
        self,
        target_id: str,
        class_name: str,
        confidence: float,
        pixel_x: float,
        pixel_y: float,
        nav_fix: NavigationalFix,
        sonar_origin: SonarScanOrigin,
        target_depth_m: Optional[float] = None,
    ) -> GeolocatedTarget:
        """Geolocate an individual detection target."""
        # 1. Pixel to track-frame offsets
        across_m, along_m = self.pixel_to_seafloor_offset(pixel_x, pixel_y, sonar_origin)

        # 2. Rotate by vehicle heading and project to WGS84
        target_coords, dist_m, bearing_deg = self.track_offsets_to_geo(
            sensor_lat=nav_fix.latitude,
            sensor_lon=nav_fix.longitude,
            heading_deg=nav_fix.heading_degrees,
            across_offset_m=across_m,
            along_offset_m=along_m,
            target_depth_m=target_depth_m,
        )

        return GeolocatedTarget(
            target_id=target_id,
            class_name=class_name,
            confidence=round(confidence, 3),
            pixel_centroid=(round(pixel_x, 1), round(pixel_y, 1)),
            across_track_offset_m=across_m,
            along_track_offset_m=along_m,
            coordinates=target_coords,
            distance_from_sensor_m=dist_m,
            bearing_degrees=bearing_deg,
        )

    def geolocate_batch(
        self,
        detections: List[Dict[str, Any]],
        nav_fix: NavigationalFix,
        sonar_origin: SonarScanOrigin,
        towfish_cfg: Optional[TowfishConfig] = None,
    ) -> BatchGeolocationResponse:
        """
        Geolocate multiple detections, apply optional towfish layback, and construct GeoJSON.
        """
        vessel_coords = None

        if towfish_cfg is not None and towfish_cfg.cable_payout_m > 0.0:
            # Coordinates provided were for the surface vessel -> calculate true towfish position
            vessel_coords = self.to_geo_coordinates(nav_fix.latitude, nav_fix.longitude)
            fish_coords, layback_dist = self.calculate_towfish_position(nav_fix, towfish_cfg)
            sensor_lat = fish_coords.latitude
            sensor_lon = fish_coords.longitude
            sensor_coords = fish_coords
            sensor_heading = nav_fix.heading_degrees
        else:
            sensor_lat = nav_fix.latitude
            sensor_lon = nav_fix.longitude
            sensor_coords = self.to_geo_coordinates(sensor_lat, sensor_lon, depth_m=nav_fix.altitude_or_depth_m)
            sensor_heading = nav_fix.heading_degrees

        geolocated_targets: List[GeolocatedTarget] = []
        geojson_features: List[GeoJSONFeature] = []

        for det in detections:
            det_id = det.get("detection_id", "unknown")
            cname = det.get("class_name", "other")
            conf = float(det.get("confidence", 0.5))

            bbox = det.get("bbox", {})
            cx = float(bbox.get("x_min", 0) + bbox.get("width", 0) / 2.0)
            cy = float(bbox.get("y_min", 0) + bbox.get("height", 0) / 2.0)

            geo_target = self.geolocate_target(
                target_id=det_id,
                class_name=cname,
                confidence=conf,
                pixel_x=cx,
                pixel_y=cy,
                nav_fix=NavigationalFix(
                    latitude=sensor_lat,
                    longitude=sensor_lon,
                    heading_degrees=sensor_heading,
                ),
                sonar_origin=sonar_origin,
            )
            geolocated_targets.append(geo_target)

            # Build RFC 7946 GeoJSON Feature
            feat = GeoJSONFeature(
                geometry=GeoJSONGeometry(
                    type="Point",
                    coordinates=[geo_target.coordinates.longitude, geo_target.coordinates.latitude],
                ),
                properties={
                    "target_id": geo_target.target_id,
                    "class_name": geo_target.class_name,
                    "confidence": geo_target.confidence,
                    "dms": geo_target.coordinates.dms_string,
                    "utm_zone": geo_target.coordinates.utm_zone,
                    "utm_easting": geo_target.coordinates.utm_easting_m,
                    "utm_northing": geo_target.coordinates.utm_northing_m,
                    "distance_m": geo_target.distance_from_sensor_m,
                    "bearing_deg": geo_target.bearing_degrees,
                    "across_track_m": geo_target.across_track_offset_m,
                    "along_track_m": geo_target.along_track_offset_m,
                },
            )
            geojson_features.append(feat)

        feature_collection = GeoJSONFeatureCollection(
            type="FeatureCollection",
            features=geojson_features,
        )

        return BatchGeolocationResponse(
            status="success",
            total_targets_geolocated=len(geolocated_targets),
            sensor_position=sensor_coords,
            vessel_position=vessel_coords,
            targets=geolocated_targets,
            geojson=feature_collection,
        )


# Global service instance
geolocation_service = GeolocationService()
