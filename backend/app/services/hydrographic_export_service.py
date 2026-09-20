"""
Hydrographic and Navigation Data Packaging and Export Service for MarineScan.

Packages completed MarineScan sonar and camera analysis results into structured,
machine-readable hydrographic and navigation datasets (JSON, CSV, GeoJSON).
Strictly operates as a presentation/export layer: consumes existing analysis
results without duplicating or altering detection, physics, geolocation, or risk logic.
"""

import csv
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("marinescan.services.hydrographic_export")

EXPORT_SCHEMA_VERSION = "1.0"


class HydrographicExportService:
    """Production service for packaging MarineScan analyses into hydrographic export formats."""

    # -------------------------------------------------------------------------
    # Helper: Data Normalization
    # -------------------------------------------------------------------------

    @staticmethod
    def _to_dict(data: Any) -> dict:
        """Converts Pydantic model or dict-like object to a plain Python dict."""
        if data is None:
            return {}
        if hasattr(data, "model_dump"):
            return data.model_dump(mode="json")
        if isinstance(data, dict):
            return data
        return dict(data)

    @classmethod
    def _extract_navigation(cls, result_dict: dict, record_meta: Optional[dict] = None) -> dict:
        """
        Extracts navigation telemetry from sonar metadata or record context.
        Preserves true coordinates and strictly keeps unlogged/missing fields as None (null).
        Never fabricates coordinates or treats (0,0) / sentinels as real GPS.
        """
        sonar_meta = result_dict.get("sonar_metadata") or {}
        nav_info = sonar_meta.get("navigation") or {}

        # Check if sonar navigation has valid coordinates
        lat = nav_info.get("latitude")
        lon = nav_info.get("longitude")
        heading = nav_info.get("heading") if nav_info.get("heading") is not None else nav_info.get("heading_deg")
        altitude = nav_info.get("altitude") if nav_info.get("altitude") is not None else nav_info.get("altitude_m")
        depth = nav_info.get("depth") if nav_info.get("depth") is not None else nav_info.get("depth_m")
        timestamp = nav_info.get("timestamp")
        source = nav_info.get("source")

        # If sonar navigation was completely absent, check if this is a standard image
        # analysis where record_meta provided vessel coordinates
        if lat is None and lon is None and record_meta:
            # Only use record_meta if it's explicitly not a sonar analysis
            if not sonar_meta:
                lat = record_meta.get("vessel_lat")
                lon = record_meta.get("vessel_lon")
                heading = record_meta.get("vessel_heading_deg")
                source = "survey_vessel_config"

        return {
            "latitude": lat,
            "longitude": lon,
            "heading": heading,
            "depth": depth,
            "altitude": altitude,
            "timestamp": timestamp,
            "source": source,
        }

    @classmethod
    def _extract_artifact_reference(cls, result_dict: dict, analysis_id: str) -> Optional[dict]:
        """
        Extracts safe artifact and raster references.
        Omits internal server filesystem paths and avoids embedding raster payloads.
        """
        sonar_meta = result_dict.get("sonar_metadata")
        if not sonar_meta:
            return None

        art_id = sonar_meta.get("artifact_id") or f"art_{analysis_id}"
        raster_ref = sonar_meta.get("raster_reference") or f"/api/v1/analyses/{analysis_id}/sonar/raster"

        return {
            "artifact_id": art_id,
            "raster_reference": raster_ref,
            "raster_width": sonar_meta.get("waterfall_width"),
            "raster_height": sonar_meta.get("waterfall_height"),
            "channel_layout": sonar_meta.get("channel_layout"),
            "selected_channels": sonar_meta.get("channels_included", []),
            "nadir_pixel_x": sonar_meta.get("nadir_pixel_x"),
            "meters_per_pixel": sonar_meta.get("meters_per_pixel"),
            "slant_range_m": sonar_meta.get("slant_range_m"),
            "total_pings": sonar_meta.get("total_pings"),
            "channel_count": sonar_meta.get("channel_count"),
            "track_artifact_id": sonar_meta.get("track_artifact_id"),
            "track_reference": sonar_meta.get("track_reference"),
        }

    # -------------------------------------------------------------------------
    # 1. JSON Export
    # -------------------------------------------------------------------------

    def export_json(
        self,
        analysis_result: Union[dict, Any],
        record_meta: Optional[dict] = None,
        analysis_id: Optional[str] = None,
    ) -> dict:
        """
        Creates a complete structured MarineScan hydrographic/navigation JSON export.
        Follows EXPORT_SCHEMA_VERSION = "1.0".
        """
        res = self._to_dict(analysis_result)
        meta = record_meta or {}
        a_id = analysis_id or res.get("mission_id") or meta.get("mission_id") or "unknown_analysis"

        sonar_meta = res.get("sonar_metadata") or {}
        img_meta = res.get("image_metadata") or {}

        # Provenance & format
        orig_filename = (
            sonar_meta.get("filename")
            or meta.get("filename")
            or img_meta.get("filename")
            or "unnamed_survey"
        )
        sonar_format = (
            sonar_meta.get("format")
            or (img_meta.get("format") if not sonar_meta else None)
            or "UNKNOWN"
        )

        navigation = self._extract_navigation(res, meta)
        artifact_ref = self._extract_artifact_reference(res, a_id)

        # Structure detections
        packaged_detections = []
        for target in res.get("targets", []):
            t_dict = self._to_dict(target)
            bbox = t_dict.get("bbox") or {}
            coords = t_dict.get("coordinates") or {}
            dims = t_dict.get("dimensions") or {}
            shadow = t_dict.get("shadow_evidence") or {}
            clearance = t_dict.get("clearance") or {}

            # Trust tier string extraction
            trust_tier = t_dict.get("trust_tier")
            if hasattr(trust_tier, "value"):
                trust_tier = trust_tier.value

            risk_tier = t_dict.get("risk_tier")
            if hasattr(risk_tier, "value"):
                risk_tier = risk_tier.value

            detection_entry = {
                "detection_id": t_dict.get("detection_id"),
                "class": t_dict.get("class_name"),
                "display_name": t_dict.get("display_name"),
                "category": t_dict.get("category"),
                "confidence": {
                    "calibrated_confidence": t_dict.get("calibrated_confidence"),
                    "ai_confidence": t_dict.get("ai_confidence"),
                    "trust_tier": trust_tier,
                    "explainability_notes": t_dict.get("explainability_notes", []),
                },
                "bbox": {
                    "coordinate_convention": "origin: top-left, X: across-track, Y: along-track",
                    "x_min": bbox.get("x_min"),
                    "y_min": bbox.get("y_min"),
                    "x_max": bbox.get("x_max"),
                    "y_max": bbox.get("y_max"),
                    "width": bbox.get("width"),
                    "height": bbox.get("height"),
                    "normalized_x_min": bbox.get("normalized_x_min"),
                    "normalized_y_min": bbox.get("normalized_y_min"),
                    "normalized_x_max": bbox.get("normalized_x_max"),
                    "normalized_y_max": bbox.get("normalized_y_max"),
                },
                "geolocation": {
                    "latitude": coords.get("latitude"),
                    "longitude": coords.get("longitude"),
                    "dms_string": coords.get("dms_string"),
                    "utm_zone": coords.get("utm_zone"),
                    "utm_easting_m": coords.get("utm_easting_m"),
                    "utm_northing_m": coords.get("utm_northing_m"),
                    "target_depth_m": coords.get("depth_m"),
                    "distance_from_sensor_m": t_dict.get("distance_from_sensor_m"),
                    "bearing_degrees": t_dict.get("bearing_degrees"),
                },
                "dimensions": {
                    "pixel_width": dims.get("pixel_width"),
                    "pixel_height": dims.get("pixel_height"),
                    "across_track_m": dims.get("across_track_m"),
                    "along_track_m": dims.get("along_track_m"),
                    "slant_range_m": dims.get("slant_range_m"),
                    "ground_range_m": dims.get("ground_range_m"),
                    "length_m": dims.get("length_m"),
                    "width_m": dims.get("width_m"),
                    "height_m": dims.get("height_m"),
                    "area_sq_m": dims.get("area_sq_m"),
                    "estimated_volume_m3": dims.get("estimated_volume_m3"),
                    "dry_mass_metric_tons": dims.get("dry_mass_metric_tons"),
                    "submerged_weight_kn": dims.get("submerged_weight_kn"),
                    "recommended_crane_lift_tons": dims.get("recommended_crane_lift_tons"),
                    "seabed_stability_index": dims.get("seabed_stability_index"),
                    "seabed_mobility_status": dims.get("seabed_mobility_status"),
                    "measurement_method": dims.get("measurement_method"),
                    "measurement_status": dims.get("measurement_status"),
                    "warnings": dims.get("warnings", []),
                },
                "shadow": {
                    "has_shadow": shadow.get("has_shadow", False),
                    "shadow_score": shadow.get("shadow_score"),
                    "cardinal_direction": shadow.get("cardinal_direction"),
                    "direction_degrees": shadow.get("direction_degrees"),
                    "shadow_length_m": shadow.get("shadow_length_m"),
                    "estimated_height_m": shadow.get("estimated_height_m"),
                },
                "risk": {
                    "risk_score": t_dict.get("risk_score"),
                    "risk_tier": risk_tier,
                    "color_hex": t_dict.get("color_hex"),
                    "water_clearance_m": clearance.get("clearance_m"),
                    "water_depth_m": clearance.get("water_depth_m"),
                    "notmar_required": t_dict.get("notmar_required") if t_dict.get("notmar_required") is not None else (t_dict.get("risk") or {}).get("notmar_required", False),
                    "notmar_status": t_dict.get("notmar_status") or (t_dict.get("risk") or {}).get("notmar_status", "NONE"),
                    "notmar_reason": t_dict.get("notmar_reason") or (t_dict.get("risk") or {}).get("notmar_reason"),
                    "geolocation_available": t_dict.get("geolocation_available") if t_dict.get("geolocation_available") is not None else (coords.get("latitude") is not None and coords.get("longitude") is not None),
                    "dimensions_available": t_dict.get("dimensions_available") if t_dict.get("dimensions_available") is not None else (dims.get("length_m") is not None or dims.get("across_track_m") is not None),
                    "action_recommendations": [
                        r.get("action_text") if isinstance(r, dict) else getattr(r, "action_text", str(r))
                        for r in t_dict.get("action_recommendations", [])
                    ],
                },
                "georeference": t_dict.get("georeference"),
            }
            packaged_detections.append(detection_entry)

        # Summary
        summary = res.get("summary") or {}

        export_package = {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "analysis": {
                "analysis_id": a_id,
                "original_filename": orig_filename,
                "sonar_format": sonar_format,
                "created_at": (
                    meta.get("created_at").isoformat()
                    if isinstance(meta.get("created_at"), datetime)
                    else meta.get("created_at")
                ),
                "status": res.get("status", "success"),
            },
            "navigation": navigation,
            "artifact": artifact_ref,
            "summary": summary,
            "detections": packaged_detections,
        }

        return export_package

    # -------------------------------------------------------------------------
    # 2. CSV Export
    # -------------------------------------------------------------------------

    def export_csv(
        self,
        analysis_result: Union[dict, Any],
        record_meta: Optional[dict] = None,
        analysis_id: Optional[str] = None,
    ) -> str:
        """
        Creates a tabular CSV detection export. One row per detected target.
        If zero targets exist, returns a valid CSV containing the complete header row.
        """
        res = self._to_dict(analysis_result)
        meta = record_meta or {}
        a_id = analysis_id or res.get("mission_id") or meta.get("mission_id") or "unknown_analysis"

        navigation = self._extract_navigation(res, meta)

        fieldnames = [
            "analysis_id",
            "detection_id",
            "class",
            "display_name",
            "category",
            "confidence",
            "ai_confidence",
            "calibrated_confidence",
            "trust_tier",
            "x_min",
            "y_min",
            "x_max",
            "y_max",
            "normalized_x_min",
            "normalized_y_min",
            "normalized_x_max",
            "normalized_y_max",
            "latitude",
            "longitude",
            "dms_string",
            "utm_zone",
            "utm_easting_m",
            "utm_northing_m",
            "distance_from_sensor_m",
            "bearing_degrees",
            "source_ping_index",
            "waterfall_row",
            "across_track_offset_m",
            "layback_applied",
            "length_m",
            "width_m",
            "height_m",
            "area_sq_m",
            "estimated_volume_m3",
            "dry_mass_metric_tons",
            "pixel_width",
            "pixel_height",
            "across_track_m",
            "along_track_m",
            "slant_range_m",
            "ground_range_m",
            "measurement_method",
            "measurement_status",
            "risk_score",
            "risk_tier",
            "water_clearance_m",
            "notmar_required",
            "notmar_status",
            "notmar_reason",
            "geolocation_available",
            "dimensions_available",
            "action_recommendations",
            "nav_latitude",
            "nav_longitude",
            "nav_heading",
            "nav_depth",
            "nav_altitude",
            "nav_timestamp",
        ]

        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for target in res.get("targets", []):
            t_dict = self._to_dict(target)
            bbox = t_dict.get("bbox") or {}
            coords = t_dict.get("coordinates") or {}
            dims = t_dict.get("dimensions") or {}
            clearance = t_dict.get("clearance") or {}

            trust_tier = t_dict.get("trust_tier")
            if hasattr(trust_tier, "value"):
                trust_tier = trust_tier.value

            risk_tier = t_dict.get("risk_tier")
            if hasattr(risk_tier, "value"):
                risk_tier = risk_tier.value

            recs = [
                r.get("action_text") if isinstance(r, dict) else getattr(r, "action_text", str(r))
                for r in t_dict.get("action_recommendations", [])
            ]

            row = {
                "analysis_id": a_id,
                "detection_id": t_dict.get("detection_id"),
                "class": t_dict.get("class_name"),
                "display_name": t_dict.get("display_name"),
                "category": t_dict.get("category"),
                "confidence": t_dict.get("calibrated_confidence"),
                "ai_confidence": t_dict.get("ai_confidence"),
                "calibrated_confidence": t_dict.get("calibrated_confidence"),
                "trust_tier": trust_tier,
                "x_min": bbox.get("x_min"),
                "y_min": bbox.get("y_min"),
                "x_max": bbox.get("x_max"),
                "y_max": bbox.get("y_max"),
                "normalized_x_min": bbox.get("normalized_x_min"),
                "normalized_y_min": bbox.get("normalized_y_min"),
                "normalized_x_max": bbox.get("normalized_x_max"),
                "normalized_y_max": bbox.get("normalized_y_max"),
                "latitude": coords.get("latitude"),
                "longitude": coords.get("longitude"),
                "dms_string": coords.get("dms_string"),
                "utm_zone": coords.get("utm_zone"),
                "utm_easting_m": coords.get("utm_easting_m"),
                "utm_northing_m": coords.get("utm_northing_m"),
                "distance_from_sensor_m": t_dict.get("distance_from_sensor_m"),
                "bearing_degrees": t_dict.get("bearing_degrees"),
                "source_ping_index": (t_dict.get("georeference") or {}).get("source_ping_index"),
                "waterfall_row": (t_dict.get("georeference") or {}).get("waterfall_row"),
                "across_track_offset_m": (t_dict.get("georeference") or {}).get("across_track_offset_m"),
                "layback_applied": (t_dict.get("georeference") or {}).get("layback_applied"),
                "length_m": dims.get("length_m"),
                "width_m": dims.get("width_m"),
                "height_m": dims.get("height_m"),
                "area_sq_m": dims.get("area_sq_m"),
                "estimated_volume_m3": dims.get("estimated_volume_m3"),
                "dry_mass_metric_tons": dims.get("dry_mass_metric_tons"),
                "pixel_width": dims.get("pixel_width"),
                "pixel_height": dims.get("pixel_height"),
                "across_track_m": dims.get("across_track_m"),
                "along_track_m": dims.get("along_track_m"),
                "slant_range_m": dims.get("slant_range_m"),
                "ground_range_m": dims.get("ground_range_m"),
                "measurement_method": dims.get("measurement_method"),
                "measurement_status": dims.get("measurement_status"),
                "risk_score": t_dict.get("risk_score"),
                "risk_tier": risk_tier,
                "water_clearance_m": clearance.get("clearance_m"),
                "notmar_required": t_dict.get("notmar_required") if t_dict.get("notmar_required") is not None else (t_dict.get("risk") or {}).get("notmar_required", False),
                "notmar_status": t_dict.get("notmar_status") or (t_dict.get("risk") or {}).get("notmar_status", "NONE"),
                "notmar_reason": t_dict.get("notmar_reason") or (t_dict.get("risk") or {}).get("notmar_reason"),
                "geolocation_available": t_dict.get("geolocation_available") if t_dict.get("geolocation_available") is not None else (coords.get("latitude") is not None and coords.get("longitude") is not None),
                "dimensions_available": t_dict.get("dimensions_available") if t_dict.get("dimensions_available") is not None else (dims.get("length_m") is not None or dims.get("across_track_m") is not None),
                "action_recommendations": " | ".join(recs),
                "nav_latitude": navigation.get("latitude"),
                "nav_longitude": navigation.get("longitude"),
                "nav_heading": navigation.get("heading"),
                "nav_depth": navigation.get("depth"),
                "nav_altitude": navigation.get("altitude"),
                "nav_timestamp": navigation.get("timestamp"),
            }
            writer.writerow(row)

        return output.getvalue()

    # -------------------------------------------------------------------------
    # 3. GeoJSON Export
    # -------------------------------------------------------------------------

    def export_geojson(
        self,
        analysis_result: Union[dict, Any],
        record_meta: Optional[dict] = None,
        analysis_id: Optional[str] = None,
    ) -> dict:
        """
        Creates a valid RFC 7946 GeoJSON FeatureCollection.
        CRITICAL: GeoJSON coordinates are strictly ordered [longitude, latitude].
        If no detections have valid coordinates, returns a valid empty FeatureCollection.
        Never fabricates coordinates or treats missing navigation as (0, 0).
        """
        res = self._to_dict(analysis_result)
        meta = record_meta or {}
        a_id = analysis_id or res.get("mission_id") or meta.get("mission_id") or "unknown_analysis"

        navigation = self._extract_navigation(res, meta)
        features: List[dict] = []

        for target in res.get("targets", []):
            t_dict = self._to_dict(target)
            coords = t_dict.get("coordinates") or {}
            lat = coords.get("latitude")
            lon = coords.get("longitude")

            # Validate WGS84 coordinates: must be numeric and not None
            if lat is None or lon is None:
                continue

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (ValueError, TypeError):
                continue

            # Verify within geographic bounds
            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                continue

            bbox = t_dict.get("bbox") or {}
            dims = t_dict.get("dimensions") or {}
            clearance = t_dict.get("clearance") or {}

            trust_tier = t_dict.get("trust_tier")
            if hasattr(trust_tier, "value"):
                trust_tier = trust_tier.value

            risk_tier = t_dict.get("risk_tier")
            if hasattr(risk_tier, "value"):
                risk_tier = risk_tier.value

            recs = [
                r.get("action_text") if isinstance(r, dict) else getattr(r, "action_text", str(r))
                for r in t_dict.get("action_recommendations", [])
            ]

            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    # RFC 7946 strictly requires [longitude, latitude]
                    "coordinates": [lon_f, lat_f],
                },
                "properties": {
                    "analysis_id": a_id,
                    "detection_id": t_dict.get("detection_id"),
                    "class": t_dict.get("class_name"),
                    "display_name": t_dict.get("display_name"),
                    "category": t_dict.get("category"),
                    "confidence": t_dict.get("calibrated_confidence"),
                    "ai_confidence": t_dict.get("ai_confidence"),
                    "trust_tier": trust_tier,
                    "dms": coords.get("dms_string"),
                    "utm_zone": coords.get("utm_zone"),
                    "utm_easting": coords.get("utm_easting_m"),
                    "utm_northing": coords.get("utm_northing_m"),
                    "distance_from_sensor_m": t_dict.get("distance_from_sensor_m"),
                    "bearing_degrees": t_dict.get("bearing_degrees"),
                    "dimensions": {
                        "pixel_width": dims.get("pixel_width"),
                        "pixel_height": dims.get("pixel_height"),
                        "across_track_m": dims.get("across_track_m"),
                        "along_track_m": dims.get("along_track_m"),
                        "slant_range_m": dims.get("slant_range_m"),
                        "ground_range_m": dims.get("ground_range_m"),
                        "length_m": dims.get("length_m"),
                        "width_m": dims.get("width_m"),
                        "height_m": dims.get("height_m"),
                        "area_sq_m": dims.get("area_sq_m"),
                        "measurement_method": dims.get("measurement_method"),
                        "measurement_status": dims.get("measurement_status"),
                    },
                    "risk": {
                        "risk_score": t_dict.get("risk_score"),
                        "risk_tier": risk_tier,
                        "water_clearance_m": clearance.get("clearance_m"),
                        "notmar_required": t_dict.get("notmar_required") if t_dict.get("notmar_required") is not None else (t_dict.get("risk") or {}).get("notmar_required", False),
                        "notmar_status": t_dict.get("notmar_status") or (t_dict.get("risk") or {}).get("notmar_status", "NONE"),
                        "notmar_reason": t_dict.get("notmar_reason") or (t_dict.get("risk") or {}).get("notmar_reason"),
                        "action_recommendations": recs,
                    },
                    "bbox": {
                        "x_min": bbox.get("x_min"),
                        "y_min": bbox.get("y_min"),
                        "x_max": bbox.get("x_max"),
                        "y_max": bbox.get("y_max"),
                        "normalized_x_min": bbox.get("normalized_x_min"),
                        "normalized_y_min": bbox.get("normalized_y_min"),
                        "normalized_x_max": bbox.get("normalized_x_max"),
                        "normalized_y_max": bbox.get("normalized_y_max"),
                    },
                    "navigation": navigation,
                    "georeference": t_dict.get("georeference"),
                    "source_ping_index": (t_dict.get("georeference") or {}).get("source_ping_index"),
                    "waterfall_row": (t_dict.get("georeference") or {}).get("waterfall_row"),
                    "across_track_offset_m": (t_dict.get("georeference") or {}).get("across_track_offset_m"),
                    "layback_applied": (t_dict.get("georeference") or {}).get("layback_applied", False),
                },
            }
            features.append(feature)

        return {
            "type": "FeatureCollection",
            "schema_version": EXPORT_SCHEMA_VERSION,
            "analysis_id": a_id,
            "features": features,
        }

    # -------------------------------------------------------------------------
    # 4. Navigation Track GeoJSON Export
    # -------------------------------------------------------------------------

    def export_track_geojson(
        self,
        track_data: Union[dict, Any],
        record_meta: Optional[dict] = None,
        analysis_id: Optional[str] = None,
    ) -> dict:
        """
        Creates a valid RFC 7946 GeoJSON FeatureCollection representing the vessel/vehicle
        sonar acquisition track.

        CRITICAL:
        - GeoJSON coordinates are strictly ordered [longitude, latitude].
        - Consecutive valid navigation points form a LineString geometry in acquisition order.
        - Points with null/missing coordinates are strictly excluded from the LineString geometry
          rather than plotted at (0, 0).
        - If >= 2 valid points: emits a LineString feature.
        - If exactly 1 valid point: emits a Point feature.
        - If 0 valid points: emits an empty FeatureCollection (features: []).
        """
        track_dict = self._to_dict(track_data)
        meta = record_meta or {}
        a_id = analysis_id or track_dict.get("analysis_id") or meta.get("mission_id") or "unknown_analysis"
        source_format = track_dict.get("source_format")
        points = track_dict.get("points", [])
        total_pings = track_dict.get("total_pings", len(points))

        valid_coords: List[List[float]] = []
        valid_timestamps: List[str] = []

        for pt in points:
            pt_dict = self._to_dict(pt)
            lat = pt_dict.get("latitude")
            lon = pt_dict.get("longitude")
            ts = pt_dict.get("timestamp")

            if ts:
                valid_timestamps.append(str(ts))

            if lat is None or lon is None:
                continue

            try:
                lat_f = float(lat)
                lon_f = float(lon)
            except (ValueError, TypeError):
                continue

            # Verify within geographic bounds
            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
                continue

            # RFC 7946 strictly requires [longitude, latitude]
            valid_coords.append([lon_f, lat_f])

        start_time = valid_timestamps[0] if valid_timestamps else None
        end_time = valid_timestamps[-1] if valid_timestamps else None

        features: List[dict] = []
        if len(valid_coords) >= 2:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": valid_coords,
                },
                "properties": {
                    "analysis_id": a_id,
                    "source_format": source_format,
                    "total_pings": total_pings,
                    "available_navigation_pings": len(valid_coords),
                    "start_timestamp": start_time,
                    "end_timestamp": end_time,
                },
            })
        elif len(valid_coords) == 1:
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": valid_coords[0],
                },
                "properties": {
                    "analysis_id": a_id,
                    "source_format": source_format,
                    "total_pings": total_pings,
                    "available_navigation_pings": 1,
                    "start_timestamp": start_time,
                    "end_timestamp": end_time,
                },
            })

        return {
            "type": "FeatureCollection",
            "schema_version": EXPORT_SCHEMA_VERSION,
            "analysis_id": a_id,
            "features": features,
        }

    # -------------------------------------------------------------------------
    # 5. Navigation Track CSV Export
    # -------------------------------------------------------------------------

    def export_track_csv(
        self,
        track_data: Union[dict, Any],
        record_meta: Optional[dict] = None,
        analysis_id: Optional[str] = None,
    ) -> str:
        """
        Creates a CSV representation of the sonar acquisition track.

        Columns:
        analysis_id,ping_index,timestamp,latitude,longitude,heading,depth,altitude

        Missing values rendered as empty strings (never fabricated as 0.0).
        Acquisition order preserved (ping_index order).
        """
        track_dict = self._to_dict(track_data)
        meta = record_meta or {}
        a_id = analysis_id or track_dict.get("analysis_id") or meta.get("mission_id") or "unknown_analysis"
        points = track_dict.get("points", [])

        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")

        headers = [
            "analysis_id",
            "ping_index",
            "timestamp",
            "latitude",
            "longitude",
            "heading",
            "depth",
            "altitude",
        ]
        writer.writerow(headers)

        for pt in points:
            pt_dict = self._to_dict(pt)
            lat = pt_dict.get("latitude")
            lon = pt_dict.get("longitude")
            ts = pt_dict.get("timestamp") or ""
            ping_idx = pt_dict.get("ping_index")

            # Support both heading/heading_deg, depth/depth_m, altitude/altitude_m
            heading = pt_dict.get("heading")
            if heading is None:
                heading = pt_dict.get("heading_deg")

            depth = pt_dict.get("depth")
            if depth is None:
                depth = pt_dict.get("depth_m")

            altitude = pt_dict.get("altitude")
            if altitude is None:
                altitude = pt_dict.get("altitude_m")

            row = [
                a_id,
                ping_idx if ping_idx is not None else "",
                ts,
                lat if lat is not None else "",
                lon if lon is not None else "",
                heading if heading is not None else "",
                depth if depth is not None else "",
                altitude if altitude is not None else "",
            ]
            writer.writerow(row)

        return output.getvalue()


# Global singleton export service instance
hydrographic_export_service = HydrographicExportService()

