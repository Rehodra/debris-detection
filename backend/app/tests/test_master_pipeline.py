"""
Unit and integration tests for the MarineScan Master Analysis Pipeline.
Tests all 12 stages: Input validation, acoustic quality check, preprocessing,
YOLO detection, candidate extraction, acoustic shadow corroboration,
ocean physics validation, confidence fusion, geolocation, dimension scaling,
maritime risk classification, and final executive reporting.
"""

import unittest
import numpy as np
import cv2
from pathlib import Path
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.services.input_service import input_service, InputValidationError
    from app.services.quality_service import quality_service
    from app.services.master_pipeline_service import master_pipeline_service
    from app.schemas.analysis import QualityTier
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.services.input_service import input_service, InputValidationError
    from backend.app.services.quality_service import quality_service
    from backend.app.services.master_pipeline_service import master_pipeline_service
    from backend.app.schemas.analysis import QualityTier


class TestMasterPipeline(unittest.TestCase):
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

    def test_input_validation_service(self):
        # Valid image bytes
        valid_bytes = self._create_sample_jpeg_bytes()
        img_bgr, meta = input_service.validate_and_decode(valid_bytes)
        self.assertEqual(meta.format, "JPEG")
        self.assertEqual(meta.width, 400)
        self.assertEqual(meta.height, 400)
        self.assertEqual(img_bgr.shape, (400, 400, 3))

        # Empty bytes should raise InputValidationError
        with self.assertRaises(InputValidationError):
            input_service.validate_and_decode(b"")

        # Corrupt data should raise InputValidationError
        with self.assertRaises(InputValidationError):
            input_service.validate_and_decode(b"random_non_image_garbage_bytes")

    def test_quality_check_service(self):
        sharp_img = np.zeros((300, 300, 3), dtype=np.uint8)
        cv2.rectangle(sharp_img, (50, 50), (250, 250), (255, 255, 255), 2)
        qa = quality_service.evaluate_image_quality(sharp_img)
        self.assertGreaterEqual(qa.overall_quality_score, 0.1)
        self.assertIn(qa.quality_tier, [QualityTier.PRISTINE, QualityTier.GOOD, QualityTier.ACCEPTABLE, QualityTier.DEGRADED])
        self.assertTrue(qa.is_usable_for_mission)

    def test_master_pipeline_execution_synthetic(self):
        img_bytes = self._create_sample_jpeg_bytes()
        result = master_pipeline_service.execute_pipeline(
            image_bytes=img_bytes,
            vessel_lat=24.86,
            vessel_lon=67.01,
            vessel_heading_deg=90.0,
            water_depth_m=20.0,
            confidence_threshold=0.20,
        )
        self.assertEqual(result.status, "success")
        self.assertTrue(result.mission_id.startswith("msn_"))
        self.assertIsNotNone(result.quality_assessment)
        self.assertIsNotNone(result.timings)
        self.assertGreater(result.timings.total_pipeline_ms, 0.0)
        self.assertEqual(result.geojson.type, "FeatureCollection")
        self.assertIsNotNone(result.summary)
        self.assertIsNotNone(result.annotated_image_base64)

    def test_master_pipeline_real_sonar_image(self):
        sonar_path = Path(__file__).resolve().parents[2] / "sample_sidescan.png"
        if not sonar_path.is_file():
            self.skipTest("sample_sidescan.png not found, skipping real sonar test.")

        with open(sonar_path, "rb") as f:
            sonar_bytes = f.read()

        result = master_pipeline_service.execute_pipeline(
            image_bytes=sonar_bytes,
            vessel_lat=24.8607,
            vessel_lon=67.0011,
            vessel_heading_deg=35.0,
            water_depth_m=18.0,
            meters_per_pixel=0.05,
            nadir_x=350.0,
            confidence_threshold=0.20,
        )

        self.assertEqual(result.status, "success")
        self.assertGreaterEqual(len(result.targets), 1)
        self.assertEqual(result.summary.total_targets_detected, len(result.targets))

        # Check target enrichment
        target1 = result.targets[0]
        self.assertIn(target1.class_name, ["shipwreck", "aircraft", "other", "fish"])
        self.assertGreater(target1.ai_confidence, 0.0)
        self.assertGreater(target1.calibrated_confidence, 0.0)
        self.assertIn("N", target1.coordinates.dms_string)
        self.assertIn("E", target1.coordinates.dms_string)
        self.assertGreater(target1.dimensions.length_m, 0.0)
        self.assertGreater(target1.dimensions.submerged_weight_kn, 0.0)
        self.assertIsNotNone(target1.risk_tier)

    def test_api_analyze_endpoint(self):
        valid_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", valid_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/analyses/analyze?vessel_lat=24.8&vessel_lon=67.1&water_depth_m=25.0&confidence_threshold=0.10",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("mission_id", data)
        self.assertIn("quality_assessment", data)
        self.assertIn("timings", data)
        self.assertIn("targets", data)
        self.assertIn("geojson", data)
        self.assertIn("summary", data)

    def test_api_visualize_endpoint(self):
        valid_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", valid_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/analyses/visualize",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertGreater(len(response.content), 100)


if __name__ == "__main__":
    unittest.main()
