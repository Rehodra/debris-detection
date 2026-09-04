"""
Unit and integration tests for MarineScan Maritime Risk Assessment Service.
Tests under-keel clearance calculation, trawl entanglement risks,
subsea infrastructure threats, environmental hazards, composite risk scoring,
action recommendations (NOTMAR, S-57), and API endpoints.
"""

import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.services.risk_service import risk_service
    from app.schemas.risk import RiskTier
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.services.risk_service import risk_service
    from backend.app.schemas.risk import RiskTier


class TestRiskService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self) -> bytes:
        img = np.full((400, 400, 3), 70, dtype=np.uint8)
        cv2.rectangle(img, (140, 140), (220, 220), (220, 220, 220), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def test_navigational_clearance_shallow_hazard(self):
        # Depth 8m, object height 5.5m -> Clearance 2.5m
        clearance, nav_risk = risk_service.calculate_navigational_clearance(
            water_depth_m=8.0,
            object_height_m=5.5,
        )
        self.assertEqual(clearance.clearance_m, 2.5)
        self.assertTrue(clearance.threatens_shallow_draft)
        self.assertTrue(clearance.threatens_medium_draft)
        self.assertTrue(clearance.threatens_deep_draft)
        self.assertEqual(nav_risk, 100.0)

    def test_navigational_clearance_deep_safe(self):
        # Depth 100m, object height 3m -> Clearance 97m
        clearance, nav_risk = risk_service.calculate_navigational_clearance(
            water_depth_m=100.0,
            object_height_m=3.0,
        )
        self.assertEqual(clearance.clearance_m, 97.0)
        self.assertFalse(clearance.threatens_shallow_draft)
        self.assertFalse(clearance.threatens_deep_draft)
        self.assertLessEqual(nav_risk, 5.0)

    def test_trawl_risk_assessment(self):
        # Large shipwreck
        wreck_risk = risk_service.evaluate_trawl_risk("shipwreck", object_height_m=4.0, length_m=35.0)
        self.assertGreaterEqual(wreck_risk, 85.0)

        # Fish target
        fish_risk = risk_service.evaluate_trawl_risk("fish", object_height_m=1.0, length_m=2.0)
        self.assertEqual(fish_risk, 0.0)

    def test_infrastructure_and_mobility_threat(self):
        # Unstable debris migrating near pipeline (50m)
        crit_infra = risk_service.evaluate_infrastructure_risk(
            class_name="other",
            mobility_status="Unstable / Migrating Debris Hazard",
            distance_to_cable_m=50.0,
        )
        self.assertGreaterEqual(crit_infra, 90.0)

        # Settled debris far from pipeline
        safe_infra = risk_service.evaluate_infrastructure_risk(
            class_name="other",
            mobility_status="Settled / Stable in Sediment",
            distance_to_cable_m=1000.0,
        )
        self.assertLessEqual(safe_infra, 30.0)

    def test_environmental_risk(self):
        # Huge shipwreck with fuel bunker hazard
        large_wreck_env = risk_service.evaluate_environmental_risk("shipwreck", volume_m3=350.0)
        self.assertEqual(large_wreck_env, 85.0)

        # Fish target
        fish_env = risk_service.evaluate_environmental_risk("fish", volume_m3=0.5)
        self.assertEqual(fish_env, 0.0)

    def test_composite_risk_and_tier_classification(self):
        # Shallow water shipwreck (depth 10m, height 7.5m)
        crit_target = risk_service.assess_target_risk(
            detection_id="wreck_crit",
            class_name="shipwreck",
            length_m=50.0,
            width_m=10.0,
            height_m=7.5,
            water_depth_m=10.0,
        )
        self.assertIn(crit_target.risk_tier, [RiskTier.CRITICAL, RiskTier.HIGH])
        self.assertTrue(crit_target.clearance.threatens_shallow_draft)
        self.assertTrue(len(crit_target.recommendations) >= 3)
        # Should contain immediate NOTMAR
        notmar_recs = [r for r in crit_target.recommendations if r.priority == "IMMEDIATE"]
        self.assertTrue(len(notmar_recs) >= 1)

        # Deep settled target (depth 90m, height 1m)
        low_target = risk_service.assess_target_risk(
            detection_id="small_deep",
            class_name="other",
            length_m=1.5,
            width_m=1.0,
            height_m=0.5,
            water_depth_m=90.0,
        )
        self.assertEqual(low_target.risk_tier, RiskTier.LOW)
        self.assertEqual(low_target.color_hex, "#2A9D8F")

    def test_api_evaluate_target_endpoint(self):
        response = self.client.post(
            f"{settings.API_V1_STR}/risk/evaluate-target?class_name=shipwreck&length_m=35.0&width_m=8.0&height_m=6.0&water_depth_m=12.0"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["class_name"], "shipwreck")
        self.assertIn("composite_risk_score", data)
        self.assertIn("risk_tier", data)
        self.assertIn("clearance", data)
        self.assertIn("recommendations", data)

    def test_api_analyze_image_endpoint(self):
        jpeg_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/risk/analyze-image?water_depth_m=15.0&confidence_threshold=0.10",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_targets_assessed", data)
        self.assertIn("results", data)


if __name__ == "__main__":
    unittest.main()
