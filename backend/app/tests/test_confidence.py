"""
Unit and integration tests for MarineScan Confidence Calibration Service.
Tests local image quality metrics (sharpness, contrast, exposure),
physics & shadow evidence synthesis, multi-source confidence fusion,
plausibility gating, trust tiering, and API endpoints.
"""

import sys
import unittest
from pathlib import Path
from typing import Tuple, List, Optional, Dict
import numpy as np
import cv2
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path for IDE & test runner compatibility
backend_root = Path(__file__).resolve().parents[2]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.main import app
from app.core.config import settings
from app.services.confidence_service import confidence_service
from app.schemas.confidence import TrustTier
from app.schemas.detection import BoundingBox
from app.schemas.shadow import ShadowAnalysisResult



class TestConfidenceService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_synthetic_sonar_target(self) -> Tuple[np.ndarray, BoundingBox]:
        img = np.full((300, 300), 75, dtype=np.uint8)
        # Highlight
        cv2.rectangle(img, (80, 80), (160, 160), 230, -1)
        # Shadow
        cv2.rectangle(img, (160, 80), (250, 160), 10, -1)

        bbox = BoundingBox(
            x_min=80.0, y_min=80.0, x_max=160.0, y_max=160.0,
            width=80.0, height=80.0,
            normalized_x_min=0.27, normalized_y_min=0.27,
            normalized_x_max=0.53, normalized_y_max=0.53,
        )
        return img, bbox

    def _create_sample_jpeg_bytes(self) -> bytes:
        img, _ = self._create_synthetic_sonar_target()
        img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        _, buf = cv2.imencode(".jpg", img_bgr)
        return buf.tobytes()

    def test_local_image_quality_sharp_vs_blurred(self):
        img_sharp, bbox = self._create_synthetic_sonar_target()
        q_sharp = confidence_service.assess_local_image_quality(img_sharp, bbox)
        self.assertGreaterEqual(q_sharp.sharpness_score, 0.70)
        self.assertIn(q_sharp.quality_tier, ["Pristine", "Good"])

        # Heavy Gaussian blur to simulate acoustic smear / turbid water
        img_blurred = cv2.GaussianBlur(img_sharp, (25, 25), 0)
        q_blurred = confidence_service.assess_local_image_quality(img_blurred, bbox)
        self.assertLess(q_blurred.sharpness_score, q_sharp.sharpness_score)

    def test_physics_confidence_with_shadow(self):
        shadow = ShadowAnalysisResult(
            detection_id="test_det",
            class_name="shipwreck",
            has_shadow=True,
            shadow_score=0.90,
            confidence_adjustment=0.12,
            quality_assessment="Strong Shadow",
        )
        score, has_shadow, is_plausible, notes = confidence_service.calculate_physics_confidence(
            class_name="shipwreck",
            length_m=30.0,
            width_m=7.0,
            shadow_result=shadow,
        )
        self.assertTrue(has_shadow)
        self.assertTrue(is_plausible)
        self.assertGreaterEqual(score, 0.90)

    def test_physics_confidence_without_shadow_penalty(self):
        # A large shipwreck with no shadow should receive lower physics confidence
        score, has_shadow, is_plausible, notes = confidence_service.calculate_physics_confidence(
            class_name="shipwreck",
            length_m=30.0,
            width_m=7.0,
            shadow_result=None,
        )
        self.assertFalse(has_shadow)
        self.assertLess(score, 0.65)

    def test_confidence_fusion_boost_verified_tier(self):
        img, bbox = self._create_synthetic_sonar_target()
        shadow = ShadowAnalysisResult(
            detection_id="test_det",
            class_name="shipwreck",
            has_shadow=True,
            shadow_score=0.95,
            confidence_adjustment=0.12,
            quality_assessment="Strong Shadow",
        )
        profile = confidence_service.evaluate_target_confidence(
            image_gray=img,
            detection_id="det_verified",
            class_name="shipwreck",
            raw_ai_confidence=0.82,
            bbox=bbox,
            length_m=28.0,
            width_m=6.5,
            shadow_result=shadow,
        )
        self.assertEqual(profile.trust_tier, TrustTier.VERIFIED_TARGET)
        self.assertGreater(profile.calibrated_confidence, 0.82)
        self.assertGreater(profile.confidence_delta, 0.0)
        self.assertTrue(len(profile.explanation_notes) >= 4)

    def test_confidence_fusion_plausibility_penalty(self):
        img, bbox = self._create_synthetic_sonar_target()
        # Impossible aircraft (400m length)
        profile = confidence_service.evaluate_target_confidence(
            image_gray=img,
            detection_id="det_impossible",
            class_name="aircraft",
            raw_ai_confidence=0.90,
            bbox=bbox,
            length_m=400.0,
            width_m=50.0,
            shadow_result=None,
        )
        self.assertFalse(profile.is_physically_plausible)
        # Should be heavily penalized
        self.assertLess(profile.calibrated_confidence, 0.55)
        self.assertIn(profile.trust_tier, [TrustTier.AMBIGUOUS_ANOMALY, TrustTier.SUSPECTED_FALSE_ALARM])

    def test_api_evaluate_target_endpoint(self):
        response = self.client.post(
            f"{settings.API_V1_STR}/confidence/evaluate-target?class_name=shipwreck&raw_ai_confidence=0.85&length_m=25.0&width_m=6.0&shadow_score=0.88"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["class_name"], "shipwreck")
        self.assertIn("calibrated_confidence", data)
        self.assertIn("trust_tier", data)
        self.assertIn("pillars", data)
        self.assertIn("explanation_notes", data)
        self.assertEqual(data["trust_tier"], "VERIFIED_TARGET")

    def test_api_analyze_image_endpoint(self):
        jpeg_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/confidence/analyze-image?confidence_threshold=0.10",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_targets_evaluated", data)
        self.assertIn("average_calibrated_confidence", data)
        self.assertIn("results", data)


if __name__ == "__main__":
    unittest.main()
