"""
Unit and Integration Tests for MarineScan Phases 10, 11, and 12:
- Phase 10: Physical Target Dimensions & Measurement
- Phase 11: Maritime Risk Assessment & NOTMAR Directives
- Phase 12: Final Result Delivery, Rich Visual Annotation & Packaging
"""

import unittest
import numpy as np
import io
import csv

from app.schemas.analysis import (
    MasterPhysicalDimensions,
    SonarMetadataContext,
    MasterTargetResult,
    ShadowEvidence,
)
from app.schemas.sonar import (
    SonarNavigationTrack,
    SonarPingTelemetry,
    SonarTargetGeoreference,
    SonarNavigation,
)
from app.schemas.detection import BoundingBox
from app.schemas.geolocation import GeoCoordinates
from app.schemas.risk import (
    RiskTier,
    NavigationalClearance,
    TargetRiskAssessment,
)
from app.schemas.shadow import ShadowAnalysisResult, ShadowDirection, ShadowExtent
from app.schemas.physics import TargetPhysicsAnalysis, ObjectPhysicalProperties, HydrodynamicStability
from app.schemas.confidence import TargetConfidenceProfile, TrustTier

from app.services.dimension_service import dimension_service
from app.services.risk_service import risk_service
from app.services.geolocation_service import geolocation_service
from app.services.hydrographic_export_service import hydrographic_export_service
from app.services.master_pipeline_service import master_pipeline_service
from app.ml.postprocess import render_detections_overlay, OVERLAY_RISK_COLORS


class TestPhases10_11_12(unittest.TestCase):
    """Comprehensive test suite for MarineScan Phases 10, 11, and 12."""

    def setUp(self):
        # 100x100 synthetic BGR test image
        self.test_bgr = np.zeros((100, 100, 3), dtype=np.uint8)

        # Base candidate detection
        self.candidate = {
            "detection_id": "target_001",
            "class_id": 0,
            "class_name": "shipwreck",
            "display_name": "Shipwreck",
            "category": "Maritime Structure",
            "confidence": 0.92,
            "bbox": {
                "x_min": 20.0,
                "y_min": 30.0,
                "x_max": 60.0,
                "y_max": 80.0,
                "width": 40.0,
                "height": 50.0,
                "normalized_x_min": 0.2,
                "normalized_y_min": 0.3,
                "normalized_x_max": 0.6,
                "normalized_y_max": 0.8,
            },
        }

    # =========================================================================
    # PHASE 10: PHYSICAL TARGET DIMENSIONS & MEASUREMENT
    # =========================================================================

    def test_camera_target_dimensions_isotropic_gsd(self):
        """Optical camera image with known GSD calculates isotropic dimensions."""
        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.05,
        )
        self.assertEqual(dims.measurement_method, "optical_camera_gsd")
        self.assertEqual(dims.measurement_status, "verified_complete")
        self.assertEqual(dims.pixel_width, 40.0)
        self.assertEqual(dims.pixel_height, 50.0)
        # width = 40 * 0.05 = 2.0m, height = 50 * 0.05 = 2.5m
        self.assertEqual(dims.across_track_m, 2.0)
        self.assertEqual(dims.along_track_m, 2.5)
        self.assertEqual(dims.length_m, 2.5)
        self.assertEqual(dims.width_m, 2.0)
        self.assertEqual(dims.area_sq_m, 5.0)
        self.assertEqual(len(dims.warnings), 0)

    def test_camera_target_dimensions_missing_gsd(self):
        """Optical camera image missing GSD sets metric dimensions to None (zero fabrication)."""
        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=None,
        )
        self.assertEqual(dims.measurement_method, "optical_camera_gsd")
        self.assertEqual(dims.measurement_status, "unavailable_missing_gsd")
        self.assertIsNone(dims.across_track_m)
        self.assertIsNone(dims.along_track_m)
        self.assertIsNone(dims.length_m)
        self.assertIsNone(dims.width_m)
        self.assertIsNone(dims.area_sq_m)
        self.assertTrue(len(dims.warnings) >= 1)
        self.assertIn("Ground sampling distance", dims.warnings[0])

    def test_sonar_dimensions_with_navigation_track(self):
        """Sonar target with valid ping track calculates along-track ping spacing."""
        sonar_ctx = SonarMetadataContext(
            format="XTF",
            filename="survey.xtf",
            total_pings=100,
            channel_count=2,
            channels_included=[0, 1],
            waterfall_width=1000,
            waterfall_height=100,
            channel_layout="port_starboard",
            nadir_pixel_x=500.0,
            meters_per_pixel=0.1,
            slant_range_m=50.0,
            navigation=SonarNavigation(latitude=24.8600, longitude=67.0000, heading=90.0, altitude=10.0),
        )

        # Track with 2 pings roughly 10 meters apart over 10 pings => ~1.0m/ping
        # 1 deg lat ~ 111,139 meters => 0.00009 deg ~ 10 meters
        track = SonarNavigationTrack(
            analysis_id="mission_01",
            source_format="XTF",
            total_pings=100,
            available_navigation_pings=2,
            points=[
                SonarPingTelemetry(ping_index=0, waterfall_row=0, latitude=24.8600, longitude=67.0000),
                SonarPingTelemetry(ping_index=10, waterfall_row=10, latitude=24.86009, longitude=67.0000),
            ],
        )

        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.1,
            sonar_context=sonar_ctx,
            navigation_track=track,
            sensor_altitude_m=10.0,
        )

        self.assertEqual(dims.measurement_method, "sonar_raster_geometry")
        self.assertEqual(dims.measurement_status, "verified_complete")
        self.assertEqual(dims.across_track_m, 4.0)  # 40px * 0.1m/px
        self.assertIsNotNone(dims.along_track_m)
        self.assertGreater(dims.along_track_m, 0.0)
        self.assertIsNotNone(dims.ground_range_m)
        self.assertIsNotNone(dims.slant_range_m)

    def test_sonar_dimensions_missing_nav_track(self):
        """Sonar target without navigation track leaves along_track_m as None (zero fabrication)."""
        sonar_ctx = SonarMetadataContext(
            format="JSF",
            filename="survey.jsf",
            total_pings=50,
            channel_count=2,
            channels_included=[0, 1],
            waterfall_width=800,
            waterfall_height=50,
            channel_layout="port_starboard",
            nadir_pixel_x=400.0,
            meters_per_pixel=0.125,
            slant_range_m=50.0,
        )

        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.125,
            sonar_context=sonar_ctx,
            navigation_track=None,
        )

        self.assertEqual(dims.measurement_method, "sonar_raster_geometry")
        self.assertEqual(dims.measurement_status, "partial_across_only")
        self.assertEqual(dims.across_track_m, 5.0)  # 40px * 0.125
        self.assertIsNone(dims.along_track_m)
        self.assertTrue(len(dims.warnings) >= 1)
        self.assertIn("Along-track ping spacing unavailable", dims.warnings[0])

    def test_sonar_dimensions_single_nav_point(self):
        """Sonar navigation track with only 1 point cannot establish ping spacing."""
        sonar_ctx = SonarMetadataContext(
            format="XTF",
            total_pings=10,
            channel_count=1,
            waterfall_width=500,
            waterfall_height=10,
            channel_layout="single_channel",
            meters_per_pixel=0.1,
        )
        track = SonarNavigationTrack(
            source_format="XTF",
            total_pings=10,
            available_navigation_pings=1,
            points=[
                SonarPingTelemetry(ping_index=0, latitude=24.8600, longitude=67.0000),
            ],
        )

        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.1,
            sonar_context=sonar_ctx,
            navigation_track=track,
        )
        self.assertEqual(dims.measurement_status, "partial_across_only")
        self.assertIsNone(dims.along_track_m)

    def test_dimensions_shadow_derived_height(self):
        """Shadow analysis result provides 3D object height off seabed."""
        from unittest.mock import MagicMock
        shadow_res = MagicMock()
        shadow_res.has_shadow = True
        shadow_res.extent.estimated_object_height_m = 3.45

        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.05,
            shadow_result=shadow_res,
        )
        self.assertEqual(dims.height_m, 3.45)

    def test_dimensions_physics_height_fallback(self):
        """TargetPhysicsAnalysis provides height when shadow result is absent."""
        from unittest.mock import MagicMock
        phy_res = MagicMock()
        phy_res.physical_properties.length_m = 12.0
        phy_res.physical_properties.width_m = 4.0
        phy_res.physical_properties.height_m = 2.8
        phy_res.physical_properties.estimated_volume_m3 = 67.2
        phy_res.physical_properties.dry_mass_metric_tons = 45.0
        phy_res.physical_properties.submerged_weight_kn = 310.0
        phy_res.physical_properties.recommended_crane_lift_tons = 67.5
        phy_res.hydrodynamic_stability.stability_index = 16.0
        phy_res.hydrodynamic_stability.mobility_status = "Settled / Stable in Sediment"

        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.05,
            shadow_result=None,
            physics_result=phy_res,
        )
        self.assertEqual(dims.height_m, 2.8)
        self.assertEqual(dims.dry_mass_metric_tons, 45.0)
        self.assertEqual(dims.recommended_crane_lift_tons, 67.5)
        self.assertEqual(dims.seabed_mobility_status, "Settled / Stable in Sediment")

    def test_dimensions_aspect_ratio_height_fallback(self):
        """Default conservative height estimation when shadow and physics are absent."""
        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.05,
            shadow_result=None,
            physics_result=None,
        )
        # min(length, width) * 0.3 = 2.0 * 0.3 = 0.6
        self.assertAlmostEqual(dims.height_m, 0.6, places=2)

    def test_dimensions_bounding_box_input_formats(self):
        """Dimension service cleanly supports both Pydantic BoundingBox and dict."""
        cand_pydantic = dict(self.candidate)
        cand_pydantic["bbox"] = BoundingBox(
            x_min=10.0, y_min=10.0, x_max=30.0, y_max=50.0,
            width=20.0, height=40.0,
            normalized_x_min=0.1, normalized_y_min=0.1, normalized_x_max=0.3, normalized_y_max=0.5
        )
        dims = dimension_service.estimate_target_dimensions(cand_pydantic, meters_per_pixel=0.1)
        self.assertEqual(dims.pixel_width, 20.0)
        self.assertEqual(dims.pixel_height, 40.0)
        self.assertEqual(dims.across_track_m, 2.0)
        self.assertEqual(dims.along_track_m, 4.0)

    def test_dimensions_batch_estimation(self):
        """Batch estimation produces complete dictionary keyed by detection_id."""
        cand2 = dict(self.candidate)
        cand2["detection_id"] = "target_002"
        batch_map = dimension_service.estimate_batch_dimensions(
            candidates=[self.candidate, cand2],
            meters_per_pixel=0.05,
        )
        self.assertIn("target_001", batch_map)
        self.assertIn("target_002", batch_map)
        self.assertEqual(batch_map["target_001"].pixel_width, 40.0)
        self.assertEqual(batch_map["target_002"].pixel_width, 40.0)

    # =========================================================================
    # PHASE 11: MARITIME RISK & NOTMAR DIRECTIVES
    # =========================================================================

    def test_risk_shallow_obstruction_with_coordinates_notmar_recommended(self):
        """Shallow clearance with verified coordinates triggers NOTMAR RECOMMENDED."""
        coords = GeoCoordinates(
            latitude=24.8610,
            longitude=67.0015,
            dms_string="24° 51' 39.6\" N, 67° 0' 5.4\" E",
            utm_zone="42N",
            utm_easting_m=300000.0,
            utm_northing_m=2750000.0,
        )
        risk = risk_service.assess_target_risk(
            detection_id="target_001",
            class_name="shipwreck",
            length_m=40.0,
            width_m=8.0,
            height_m=8.0,
            water_depth_m=10.0,  # clearance = 10 - 8 = 2.0m <= 3.5m (shallow hazard)
            coordinates=coords,
        )
        self.assertTrue(risk.clearance.threatens_shallow_draft)
        self.assertTrue(risk.geolocation_available)
        self.assertTrue(risk.dimensions_available)
        self.assertTrue(risk.notmar_required)
        self.assertEqual(risk.notmar_status, "RECOMMENDED")
        self.assertIn("Shallow submerged obstruction", risk.notmar_reason)
        notmar_recs = [r for r in risk.recommendations if r.priority == "IMMEDIATE"]
        self.assertTrue(len(notmar_recs) >= 1)

    def test_risk_shallow_obstruction_missing_coordinates_unknown_status(self):
        """Shallow clearance without coordinates flags UNKNOWN_INSUFFICIENT_DATA (no fabrication)."""
        risk = risk_service.assess_target_risk(
            detection_id="target_unnav",
            class_name="shipwreck",
            length_m=40.0,
            width_m=8.0,
            height_m=8.0,
            water_depth_m=10.0,
            coordinates=None,
            georeference=None,
        )
        self.assertTrue(risk.clearance.threatens_shallow_draft)
        self.assertFalse(risk.geolocation_available)
        self.assertFalse(risk.notmar_required)
        self.assertEqual(risk.notmar_status, "UNKNOWN_INSUFFICIENT_DATA")
        self.assertIn("unrecorded", risk.notmar_reason)
        self.assertTrue(any("lacks verified geographic coordinates" in w for w in risk.warnings))

    def test_risk_critical_hazard_suspected_false_alarm_monitored(self):
        """Critical collision threat flagged as SUSPECTED_FALSE_ALARM is marked MONITOR."""
        from unittest.mock import MagicMock
        conf_profile = MagicMock()
        conf_profile.trust_tier = TrustTier.SUSPECTED_FALSE_ALARM
        coords = geolocation_service.to_geo_coordinates(24.86, 67.00)

        risk = risk_service.assess_target_risk(
            detection_id="target_fa",
            class_name="shipwreck",
            length_m=30.0,
            width_m=5.0,
            height_m=8.0,
            water_depth_m=10.0,
            confidence_profile=conf_profile,
            coordinates=coords,
        )
        self.assertFalse(risk.notmar_required)
        self.assertEqual(risk.notmar_status, "MONITOR")
        self.assertIn("suspected false alarm", risk.notmar_reason)

    def test_risk_safe_water_clearance_no_notmar(self):
        """Safe deep water clearance results in NOTMAR status NONE."""
        coords = geolocation_service.to_geo_coordinates(24.86, 67.00)
        risk = risk_service.assess_target_risk(
            detection_id="target_deep",
            class_name="other",
            length_m=2.0,
            width_m=1.0,
            height_m=0.5,
            water_depth_m=80.0,  # clearance = 79.5m
            coordinates=coords,
        )
        self.assertFalse(risk.clearance.threatens_shallow_draft)
        self.assertFalse(risk.notmar_required)
        self.assertEqual(risk.notmar_status, "NONE")
        self.assertIn("Adequate navigational clearance", risk.notmar_reason)

    def test_risk_fish_target_exempt_from_notmar(self):
        """Biological biomass (fish) never triggers a NOTMAR broadcast."""
        coords = geolocation_service.to_geo_coordinates(24.86, 67.00)
        risk = risk_service.assess_target_risk(
            detection_id="fish_target",
            class_name="fish",
            length_m=1.0,
            width_m=0.3,
            height_m=0.3,
            water_depth_m=5.0,
            coordinates=coords,
        )
        self.assertFalse(risk.notmar_required)
        self.assertEqual(risk.notmar_status, "NONE")
        self.assertEqual(risk.composite_risk_score, 5.0)

    def test_risk_batch_immediate_notmar_flag_true(self):
        """Batch evaluation sets immediate_notmar_required=True when any target requires NOTMAR."""
        coords = geolocation_service.to_geo_coordinates(24.86, 67.00)
        geo_map = {"target_001": type("GeoItem", (), {"coordinates": coords, "georeference": None})()}
        
        batch = risk_service.assess_batch_risk(
            detections=[self.candidate],
            water_depth_m=3.0,  # Very shallow => triggers NOTMAR
            meters_per_pixel=0.05,
            geo_map=geo_map,
        )
        self.assertTrue(batch.immediate_notmar_required)
        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].notmar_status, "RECOMMENDED")

    def test_risk_batch_immediate_notmar_flag_false(self):
        """Batch evaluation sets immediate_notmar_required=False when all targets are safe."""
        batch = risk_service.assess_batch_risk(
            detections=[self.candidate],
            water_depth_m=100.0,  # Very deep
            meters_per_pixel=0.05,
        )
        self.assertFalse(batch.immediate_notmar_required)

    def test_risk_service_backward_compatibility(self):
        """Calling risk_service without new optional maps works without error."""
        batch = risk_service.assess_batch_risk(
            detections=[self.candidate],
            water_depth_m=30.0,
        )
        self.assertEqual(batch.status, "success")
        self.assertEqual(len(batch.results), 1)

    # =========================================================================
    # PHASE 12: VISUAL OVERLAY ANNOTATION & PACKAGING
    # =========================================================================

    def test_overlay_risk_color_critical(self):
        """Critical hazard bounding box uses crimson red."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {
            "display_name": "Wreck",
            "confidence": 0.95,
            "risk_tier": "CRITICAL",
            "bbox": {"x_min": 10, "y_min": 10, "x_max": 40, "y_max": 40},
        }
        annotated = render_detections_overlay(img, [det])
        self.assertEqual(annotated.shape, (100, 100, 3))
        # Top-left box outline pixel should match CRITICAL BGR (70, 57, 230)
        self.assertEqual(tuple(annotated[10, 10]), OVERLAY_RISK_COLORS["CRITICAL"])

    def test_overlay_risk_color_high(self):
        """High hazard bounding box uses deep orange."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {
            "display_name": "Obstruction",
            "confidence": 0.85,
            "risk_tier": "HIGH",
            "bbox": {"x_min": 10, "y_min": 10, "x_max": 40, "y_max": 40},
        }
        annotated = render_detections_overlay(img, [det])
        self.assertEqual(tuple(annotated[10, 10]), OVERLAY_RISK_COLORS["HIGH"])

    def test_overlay_risk_color_low(self):
        """Low hazard bounding box uses teal/green."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {
            "display_name": "Anchor",
            "confidence": 0.70,
            "risk_tier": "LOW",
            "bbox": {"x_min": 10, "y_min": 10, "x_max": 40, "y_max": 40},
        }
        annotated = render_detections_overlay(img, [det])
        self.assertEqual(tuple(annotated[10, 10]), OVERLAY_RISK_COLORS["LOW"])

    def test_overlay_label_dimensions_and_geo_tag(self):
        """Overlay renders without error when dimensions and georeferenced badges are active."""
        img = np.zeros((200, 300, 3), dtype=np.uint8)
        det = {
            "display_name": "Shipwreck",
            "confidence": 0.94,
            "risk_tier": "CRITICAL",
            "length_m": 18.2,
            "width_m": 4.5,
            "coordinates": {"latitude": 24.86, "longitude": 67.00},
            "bbox": {"x_min": 50, "y_min": 50, "x_max": 150, "y_max": 150},
        }
        annotated = render_detections_overlay(img, [det])
        self.assertEqual(annotated.shape, (200, 300, 3))
        # Ensure image was drawn on
        self.assertTrue(np.any(annotated > 0))

    def test_overlay_label_fallback_when_metrics_absent(self):
        """Overlay renders cleanly when dimensions and georeference are absent."""
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        det = {
            "display_name": "Debris",
            "confidence": 0.80,
            "bbox": {"x_min": 20, "y_min": 20, "x_max": 60, "y_max": 60},
        }
        annotated = render_detections_overlay(img, [det])
        self.assertEqual(annotated.shape, (100, 100, 3))

    # =========================================================================
    # PHASE 12: HYDROGRAPHIC EXPORT PACKAGING
    # =========================================================================

    def test_export_json_includes_phase_10_and_11_fields(self):
        """JSON export includes enriched dimensions and NOTMAR properties."""
        mock_analysis = {
            "mission_id": "test_json_export",
            "status": "success",
            "targets": [
                {
                    "detection_id": "tgt_01",
                    "class_name": "shipwreck",
                    "display_name": "Shipwreck",
                    "category": "Structure",
                    "ai_confidence": 0.95,
                    "calibrated_confidence": 0.93,
                    "trust_tier": "VERIFIED_TARGET",
                    "bbox": {"x_min": 10, "y_min": 10, "x_max": 50, "y_max": 60},
                    "coordinates": {"latitude": 24.861, "longitude": 67.002, "dms_string": "24N 67E"},
                    "dimensions": {
                        "pixel_width": 40.0,
                        "pixel_height": 50.0,
                        "across_track_m": 4.0,
                        "along_track_m": 5.0,
                        "length_m": 5.0,
                        "width_m": 4.0,
                        "height_m": 2.5,
                        "measurement_method": "sonar_raster_geometry",
                        "measurement_status": "verified_complete",
                    },
                    "risk_score": 85.0,
                    "risk_tier": "CRITICAL",
                    "notmar_required": True,
                    "notmar_status": "RECOMMENDED",
                    "notmar_reason": "Shallow obstruction",
                    "clearance": {"water_depth_m": 10.0, "clearance_m": 2.0},
                }
            ],
        }

        pkg = hydrographic_export_service.export_json(mock_analysis)
        self.assertEqual(pkg["schema_version"], "1.0")
        self.assertEqual(len(pkg["detections"]), 1)
        det_entry = pkg["detections"][0]

        # Verify Phase 10 Dimensions in JSON
        dims = det_entry["dimensions"]
        self.assertEqual(dims["pixel_width"], 40.0)
        self.assertEqual(dims["across_track_m"], 4.0)
        self.assertEqual(dims["measurement_status"], "verified_complete")

        # Verify Phase 11 NOTMAR in JSON
        risk = det_entry["risk"]
        self.assertTrue(risk["notmar_required"])
        self.assertEqual(risk["notmar_status"], "RECOMMENDED")
        self.assertEqual(risk["notmar_reason"], "Shallow obstruction")

    def test_export_csv_includes_phase_10_and_11_columns(self):
        """CSV export header and rows include new dimension and NOTMAR columns."""
        mock_analysis = {
            "mission_id": "test_csv_export",
            "targets": [
                {
                    "detection_id": "tgt_02",
                    "class_name": "pipe",
                    "display_name": "Pipeline",
                    "category": "Infrastructure",
                    "ai_confidence": 0.88,
                    "calibrated_confidence": 0.85,
                    "trust_tier": "PROBABLE_DEBRIS",
                    "bbox": {"x_min": 5, "y_min": 5, "x_max": 25, "y_max": 45},
                    "coordinates": {"latitude": 24.865, "longitude": 67.005},
                    "dimensions": {
                        "pixel_width": 20.0,
                        "pixel_height": 40.0,
                        "across_track_m": 2.0,
                        "along_track_m": 4.0,
                        "length_m": 4.0,
                        "width_m": 2.0,
                        "height_m": 1.0,
                        "measurement_method": "optical_camera_gsd",
                        "measurement_status": "verified_complete",
                    },
                    "risk_score": 50.0,
                    "risk_tier": "MODERATE",
                    "notmar_required": False,
                    "notmar_status": "NONE",
                    "notmar_reason": "Adequate clearance",
                    "clearance": {"water_depth_m": 30.0, "clearance_m": 29.0},
                }
            ],
        }

        csv_str = hydrographic_export_service.export_csv(mock_analysis)
        reader = csv.DictReader(io.StringIO(csv_str))
        rows = list(reader)
        self.assertEqual(len(rows), 1)
        row = rows[0]

        # Verify columns exist and are populated
        self.assertIn("pixel_width", row)
        self.assertEqual(row["pixel_width"], "20.0")
        self.assertIn("across_track_m", row)
        self.assertEqual(row["across_track_m"], "2.0")
        self.assertIn("notmar_required", row)
        self.assertEqual(row["notmar_required"], "False")
        self.assertIn("notmar_status", row)
        self.assertEqual(row["notmar_status"], "NONE")

    def test_export_geojson_includes_dimensions_and_notmar(self):
        """GeoJSON export feature properties contain enriched dimensions and risk."""
        mock_analysis = {
            "mission_id": "test_geojson_export",
            "targets": [
                {
                    "detection_id": "tgt_geo",
                    "class_name": "shipwreck",
                    "display_name": "Shipwreck",
                    "category": "Structure",
                    "ai_confidence": 0.90,
                    "calibrated_confidence": 0.88,
                    "trust_tier": "VERIFIED_TARGET",
                    "coordinates": {"latitude": 24.8612, "longitude": 67.0018},
                    "dimensions": {
                        "pixel_width": 30.0,
                        "pixel_height": 60.0,
                        "across_track_m": 3.0,
                        "along_track_m": 6.0,
                        "length_m": 6.0,
                        "width_m": 3.0,
                        "height_m": 2.0,
                        "measurement_method": "sonar_raster_geometry",
                        "measurement_status": "verified_complete",
                    },
                    "risk_score": 82.0,
                    "risk_tier": "CRITICAL",
                    "notmar_required": True,
                    "notmar_status": "RECOMMENDED",
                    "notmar_reason": "Critical collision threat",
                    "clearance": {"water_depth_m": 5.0, "clearance_m": 1.5},
                }
            ],
        }

        geojson = hydrographic_export_service.export_geojson(mock_analysis)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 1)
        feat = geojson["features"][0]

        # Strict RFC 7946 [longitude, latitude]
        self.assertEqual(feat["geometry"]["coordinates"], [67.0018, 24.8612])

        props = feat["properties"]
        self.assertEqual(props["dimensions"]["pixel_width"], 30.0)
        self.assertEqual(props["dimensions"]["across_track_m"], 3.0)
        self.assertEqual(props["dimensions"]["measurement_status"], "verified_complete")
        self.assertTrue(props["risk"]["notmar_required"])
        self.assertEqual(props["risk"]["notmar_status"], "RECOMMENDED")

    def test_export_geojson_omits_unnavigated_targets(self):
        """GeoJSON export strictly omits targets without coordinates (never fabricates (0,0))."""
        mock_analysis = {
            "mission_id": "test_omit_unnav",
            "targets": [
                {
                    "detection_id": "tgt_no_geo",
                    "class_name": "debris",
                    "coordinates": None,  # No coordinates
                }
            ],
        }
        geojson = hydrographic_export_service.export_geojson(mock_analysis)
        self.assertEqual(len(geojson["features"]), 0)

    # =========================================================================
    # END-TO-END MASTER PIPELINE INTEGRATION
    # =========================================================================

    def test_master_pipeline_e2e_camera_backward_compatibility(self):
        """Full 12-stage pipeline on camera image executes with complete backward compatibility."""
        import cv2
        _, img_encoded = cv2.imencode(".png", self.test_bgr)
        image_bytes = img_encoded.tobytes()

        res = master_pipeline_service.execute_pipeline(
            image_bytes=image_bytes,
            vessel_lat=24.8607,
            vessel_lon=67.0011,
            meters_per_pixel=0.05,
            return_visualization=True,
        )

        self.assertEqual(res.status, "success")
        self.assertIsNotNone(res.timings.dimension_estimate_ms)
        self.assertIsNotNone(res.timings.risk_classification_ms)
        self.assertTrue(hasattr(res.summary, "immediate_notmar_required"))

    def test_dimensions_ground_and_slant_range_calculation(self):
        """Dimension service computes ground range and slant range based on nadir pixel and altitude."""
        sonar_ctx = SonarMetadataContext(
            format="XTF",
            total_pings=50,
            channel_count=2,
            waterfall_width=1000,
            waterfall_height=50,
            channel_layout="port_starboard",
            nadir_pixel_x=500.0,
            meters_per_pixel=0.1,
            slant_range_m=50.0,
        )
        # Center x of candidate is (20 + 60) / 2 = 40.0. Nadir is 500.0.
        # dx = 460 pixels * 0.1m/px = 46.0m ground range.
        # altitude = 10.0m => slant range = sqrt(46^2 + 10^2) = sqrt(2116 + 100) = sqrt(2216) ~ 47.07m
        dims = dimension_service.estimate_target_dimensions(
            candidate=self.candidate,
            meters_per_pixel=0.1,
            sonar_context=sonar_ctx,
            sensor_altitude_m=10.0,
        )
        self.assertEqual(dims.ground_range_m, 46.0)
        self.assertAlmostEqual(dims.slant_range_m, 47.07, places=1)

    def test_risk_factors_breakdown(self):
        """Risk factors breakdown contains valid 0-100 scores across all 5 dimensions."""
        coords = geolocation_service.to_geo_coordinates(24.86, 67.00)
        risk = risk_service.assess_target_risk(
            detection_id="tgt_fac",
            class_name="ghost_net",
            length_m=20.0,
            width_m=5.0,
            height_m=1.0,
            water_depth_m=20.0,
            coordinates=coords,
        )
        factors = risk.factors
        for val in [factors.navigational_risk, factors.trawl_risk, factors.infrastructure_risk,
                    factors.environmental_risk, factors.mobility_risk]:
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 100.0)

    def test_target_dimensions_alias_and_schema_types(self):
        """TargetDimensions alias is equivalent to MasterPhysicalDimensions."""
        from app.schemas.analysis import TargetDimensions
        self.assertIs(TargetDimensions, MasterPhysicalDimensions)

    def test_master_pipeline_e2e_target_synthesis(self):
        """Master pipeline returns targets synthesized with all Phase 10-12 attributes."""
        import cv2
        _, img_encoded = cv2.imencode(".png", self.test_bgr)
        res = master_pipeline_service.execute_pipeline(
            image_bytes=img_encoded.tobytes(),
            vessel_lat=24.8607,
            vessel_lon=67.0011,
            meters_per_pixel=0.05,
            return_visualization=False,
        )
        self.assertEqual(res.status, "success")
        for target in res.targets:
            self.assertIsInstance(target.dimensions, MasterPhysicalDimensions)
            self.assertIsNotNone(target.dimensions.pixel_width)
            self.assertIsNotNone(target.dimensions.pixel_height)
            self.assertIsNotNone(target.dimensions.measurement_method)
            self.assertIsNotNone(target.dimensions.measurement_status)
            self.assertIn(target.risk_tier, [RiskTier.CRITICAL, RiskTier.HIGH, RiskTier.MODERATE, RiskTier.LOW])


if __name__ == "__main__":
    unittest.main()
