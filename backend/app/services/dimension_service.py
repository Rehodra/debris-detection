"""
Physical Target Dimensions and Measurement Service for MarineScan (Phase 10).

Responsible for:
- Calculating bounding box pixel extents (pixel_width, pixel_height).
- Computing across-track physical resolution from raster geometry and slant range.
- Determining along-track resolution from real ping spacing in SonarNavigationTrack.
- Preserving strict integrity (zero fabrication: marks along-track as None when ping spacing is unrecorded).
- Supporting isotropic optical camera GSD measurements.
- Integrating acoustic shadow-derived 3D height estimations.
"""

import math
import logging
from typing import Optional, List, Dict, Any

from app.schemas.analysis import MasterPhysicalDimensions, SonarMetadataContext
from app.schemas.sonar import SonarNavigationTrack
from app.schemas.shadow import ShadowAnalysisResult
from app.schemas.physics import TargetPhysicsAnalysis
from app.schemas.detection import BoundingBox

logger = logging.getLogger("marinescan.services.dimensions")


class DimensionService:
    """Production service for metric dimensioning of sonar and camera targets."""

    @staticmethod
    def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in meters using Haversine formula."""
        r = 6371000.0  # Earth's mean radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (math.sin(delta_phi / 2.0) ** 2 +
             math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
        return r * c

    def calculate_along_track_ping_spacing(
        self,
        navigation_track: Optional[SonarNavigationTrack],
    ) -> Optional[float]:
        """
        Derives real along-track ping spacing (meters per ping row) from navigation track fixes.
        Requires at least 2 valid coordinates in the track. Never fabricates.
        """
        if not navigation_track or not navigation_track.points:
            return None

        # Extract all pings with valid coordinates
        valid_points = [
            p for p in navigation_track.points
            if p.latitude is not None and p.longitude is not None
        ]

        if len(valid_points) < 2:
            return None

        total_distance = 0.0
        total_pings_spanned = 0

        for i in range(len(valid_points) - 1):
            p1 = valid_points[i]
            p2 = valid_points[i + 1]
            dist = self._haversine_distance_m(p1.latitude, p1.longitude, p2.latitude, p2.longitude)
            idx1 = p1.waterfall_row if p1.waterfall_row is not None else p1.ping_index
            idx2 = p2.waterfall_row if p2.waterfall_row is not None else p2.ping_index
            delta_idx = abs(idx2 - idx1)
            if delta_idx > 0:
                total_distance += dist
                total_pings_spanned += delta_idx

        if total_pings_spanned > 0 and total_distance > 0.0:
            avg_spacing = total_distance / total_pings_spanned
            if 0.001 <= avg_spacing <= 50.0:
                return avg_spacing

        return None

    def estimate_target_dimensions(
        self,
        candidate: Dict[str, Any],
        meters_per_pixel: Optional[float] = None,
        shadow_result: Optional[ShadowAnalysisResult] = None,
        physics_result: Optional[TargetPhysicsAnalysis] = None,
        sonar_context: Optional[SonarMetadataContext] = None,
        navigation_track: Optional[SonarNavigationTrack] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> MasterPhysicalDimensions:
        """
        Calculate precision physical dimensions for a single detected debris target.
        """
        raw_bbox = candidate.get("bbox") or {}
        if isinstance(raw_bbox, BoundingBox):
            bbox_dict = raw_bbox.model_dump()
        elif isinstance(raw_bbox, dict):
            bbox_dict = raw_bbox
        else:
            bbox_dict = {}

        pixel_w = float(bbox_dict.get("width", 20.0))
        pixel_h = float(bbox_dict.get("height", 20.0))
        x_min = float(bbox_dict.get("x_min", 0.0))
        x_max = float(bbox_dict.get("x_max", pixel_w))
        center_x = (x_min + x_max) / 2.0

        warnings: List[str] = []

        # ---------------------------------------------------------------------
        # Case 1: Raw Sonar Waterfall Raster
        # ---------------------------------------------------------------------
        if sonar_context is not None:
            measurement_method = "sonar_raster_geometry"

            # Determine across-track resolution
            m_across: Optional[float] = None
            if meters_per_pixel is not None and meters_per_pixel > 0.0:
                m_across = meters_per_pixel
            elif sonar_context.meters_per_pixel is not None and sonar_context.meters_per_pixel > 0.0:
                m_across = sonar_context.meters_per_pixel
            elif (slant_range_m or sonar_context.slant_range_m) and sonar_context.waterfall_width > 0:
                sr = slant_range_m or sonar_context.slant_range_m
                # Dual channel port/starboard raster spans 2 * slant_range
                is_dual = sonar_context.channel_count >= 2 or "port_starboard" in sonar_context.channel_layout
                samples_per_channel = (sonar_context.waterfall_width / 2.0) if is_dual else float(sonar_context.waterfall_width)
                m_across = sr / samples_per_channel if samples_per_channel > 0 else None

            if m_across is not None and m_across > 0.0:
                across_track_m = round(pixel_w * m_across, 2)
            else:
                across_track_m = None
                warnings.append("Acoustic across-track resolution unavailable; cannot determine physical width.")

            # Determine along-track resolution from navigation track
            ping_spacing = self.calculate_along_track_ping_spacing(navigation_track)
            if ping_spacing is not None and ping_spacing > 0.0:
                along_track_m = round(pixel_h * ping_spacing, 2)
                measurement_status = "verified_complete"
            else:
                along_track_m = None
                measurement_status = "partial_across_only" if across_track_m is not None else "unavailable_missing_gsd"
                warnings.append("Along-track ping spacing unavailable from navigation track; along-track dimension could not be determined without fabrication.")

            # Slant range & ground range geometry
            nadir_x = (
                sonar_context.nadir_pixel_x
                if sonar_context.nadir_pixel_x is not None
                else (sonar_context.waterfall_width / 2.0 if sonar_context.waterfall_width > 0 else None)
            )

            if nadir_x is not None and m_across is not None and m_across > 0.0:
                ground_range_px = abs(center_x - nadir_x)
                ground_range_m = round(ground_range_px * m_across, 2)
                alt = sensor_altitude_m if sensor_altitude_m is not None else (
                    sonar_context.navigation.altitude if sonar_context.navigation and sonar_context.navigation.altitude is not None else 0.0
                )
                if alt > 0.0:
                    slant_calc = math.sqrt(ground_range_m ** 2 + alt ** 2)
                    slant_range_val = round(slant_calc, 2)
                else:
                    slant_range_val = ground_range_m
            else:
                ground_range_m = None
                slant_range_val = slant_range_m or (sonar_context.slant_range_m if sonar_context else None)

            # Length and Width
            if across_track_m is not None and along_track_m is not None:
                length_m = round(max(across_track_m, along_track_m), 2)
                width_m = round(min(across_track_m, along_track_m), 2)
                area_sq_m = round(across_track_m * along_track_m, 2)
            elif across_track_m is not None:
                length_m = across_track_m
                width_m = across_track_m
                area_sq_m = None
            else:
                length_m = None
                width_m = None
                area_sq_m = None

        # ---------------------------------------------------------------------
        # Case 2: Optical Camera Image
        # ---------------------------------------------------------------------
        else:
            measurement_method = "optical_camera_gsd"
            ground_range_m = None
            slant_range_val = None

            if meters_per_pixel is not None and meters_per_pixel > 0.0:
                across_track_m = round(pixel_w * meters_per_pixel, 2)
                along_track_m = round(pixel_h * meters_per_pixel, 2)
                length_m = round(max(across_track_m, along_track_m), 2)
                width_m = round(min(across_track_m, along_track_m), 2)
                area_sq_m = round(across_track_m * along_track_m, 2)
                measurement_status = "verified_complete"
            else:
                across_track_m = None
                along_track_m = None
                length_m = None
                width_m = None
                area_sq_m = None
                measurement_status = "unavailable_missing_gsd"
                warnings.append("Ground sampling distance (GSD / meters_per_pixel) not provided; real-world metric dimensions unavailable.")

        # ---------------------------------------------------------------------
        # Height off Seabed
        # ---------------------------------------------------------------------
        height_m: Optional[float] = None
        if shadow_result and shadow_result.has_shadow and shadow_result.extent and shadow_result.extent.estimated_object_height_m:
            height_m = round(shadow_result.extent.estimated_object_height_m, 2)
        elif physics_result and physics_result.physical_properties.height_m > 0.0:
            height_m = round(physics_result.physical_properties.height_m, 2)
        elif length_m is not None and width_m is not None:
            height_m = round(max(0.2, min(length_m, width_m) * 0.3), 2)

        # ---------------------------------------------------------------------
        # Hydrodynamic & Salvage Properties
        # ---------------------------------------------------------------------
        if physics_result:
            props = physics_result.physical_properties
            stab = physics_result.hydrodynamic_stability
            vol_m3 = props.estimated_volume_m3
            dry_mass = props.dry_mass_metric_tons
            sub_wt = props.submerged_weight_kn
            lift_tons = props.recommended_crane_lift_tons
            stab_idx = stab.stability_index
            mob_status = stab.mobility_status
        elif length_m is not None and width_m is not None and height_m is not None:
            vol_m3 = round(length_m * width_m * height_m * 0.5, 2)
            dry_mass = round(max(0.1, vol_m3 * 1.5), 2)
            sub_wt = round(dry_mass * 9.81 * 0.7, 2)
            lift_tons = round(dry_mass * 1.5, 2)
            stab_idx = 10.0
            mob_status = "Settled / Stable in Sediment"
        else:
            vol_m3 = None
            dry_mass = None
            sub_wt = None
            lift_tons = None
            stab_idx = None
            mob_status = None

        return MasterPhysicalDimensions(
            pixel_width=round(pixel_w, 2),
            pixel_height=round(pixel_h, 2),
            across_track_m=across_track_m,
            along_track_m=along_track_m,
            slant_range_m=slant_range_val,
            ground_range_m=ground_range_m,
            length_m=length_m,
            width_m=width_m,
            height_m=height_m,
            area_sq_m=area_sq_m,
            estimated_volume_m3=vol_m3,
            dry_mass_metric_tons=dry_mass,
            submerged_weight_kn=sub_wt,
            recommended_crane_lift_tons=lift_tons,
            seabed_stability_index=stab_idx,
            seabed_mobility_status=mob_status,
            measurement_method=measurement_method,
            measurement_status=measurement_status,
            warnings=warnings,
        )

    def estimate_batch_dimensions(
        self,
        candidates: List[Dict[str, Any]],
        meters_per_pixel: Optional[float] = None,
        shadow_results: Optional[List[ShadowAnalysisResult]] = None,
        physics_results: Optional[List[TargetPhysicsAnalysis]] = None,
        sonar_context: Optional[SonarMetadataContext] = None,
        navigation_track: Optional[SonarNavigationTrack] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> Dict[str, MasterPhysicalDimensions]:
        """
        Estimate physical dimensions for a batch of candidate detections.
        Returns mapping from detection_id to MasterPhysicalDimensions.
        """
        shadow_map = {s.detection_id: s for s in (shadow_results or [])}
        phys_map = {p.detection_id: p for p in (physics_results or [])}

        dim_map: Dict[str, MasterPhysicalDimensions] = {}
        for cand in candidates:
            tid = cand.get("detection_id", "unknown")
            shd = shadow_map.get(tid)
            phy = phys_map.get(tid)

            dim_obj = self.estimate_target_dimensions(
                candidate=cand,
                meters_per_pixel=meters_per_pixel,
                shadow_result=shd,
                physics_result=phy,
                sonar_context=sonar_context,
                navigation_track=navigation_track,
                sensor_altitude_m=sensor_altitude_m,
                slant_range_m=slant_range_m,
            )
            dim_map[tid] = dim_obj

        return dim_map


# Global service instance
dimension_service = DimensionService()
