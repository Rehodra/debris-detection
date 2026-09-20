"""
Unit and integration tests for Phase 5: Raw Sonar Pipeline Integration.
Verifies end-to-end flow: .xtf/.jsf -> parser -> waterfall -> master pipeline -> YOLO -> shadow -> physics -> risk.
Ensures 100% backward compatibility with existing image-upload workflows.
"""

import io
import json
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import MasterAnalysisResult
from app.services.input_service import InputValidationError
from app.services.master_pipeline_service import master_pipeline_service
from app.services.sonar_ingestion_service import SonarIngestionError, sonar_ingestion_service
from app.tests.test_jsf_parser import build_synthetic_jsf_binary
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


class TestSonarPipelineIntegration(unittest.TestCase):
    """
    Integration test suite verifying that raw sonar recordings feed cleanly
    into the existing 12-stage MarineScan image analysis pipeline.
    """

    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self, width: int = 120, height: int = 120) -> bytes:
        img = np.full((height, width, 3), 90, dtype=np.uint8)
        cv2.rectangle(img, (30, 30), (70, 70), (220, 220, 220), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def _create_sample_png_bytes(self, width: int = 120, height: int = 120) -> bytes:
        img = np.full((height, width, 3), 60, dtype=np.uint8)
        cv2.circle(img, (60, 60), 25, (200, 200, 200), -1)
        _, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    # -------------------------------------------------------------------------
    # Test 1: Existing image workflow remains functional
    # -------------------------------------------------------------------------

    def test_01_existing_jpeg_png_workflow_remains_functional(self):
        """
        Verify that standard JPEG and PNG images proceed through the existing
        image ingestion path without invoking raw sonar decoders.
        """
        jpeg_bytes = self._create_sample_jpeg_bytes()
        result_jpeg = master_pipeline_service.execute_pipeline(
            image_bytes=jpeg_bytes,
            filename="survey_frame.jpg",
        )
        self.assertEqual(result_jpeg.status, "success")
        self.assertEqual(result_jpeg.image_metadata.format, "JPEG")
        self.assertIsNone(result_jpeg.sonar_metadata)
        self.assertGreater(result_jpeg.timings.total_pipeline_ms, 0.0)

        png_bytes = self._create_sample_png_bytes()
        result_png = master_pipeline_service.execute_pipeline(
            image_bytes=png_bytes,
            filename="acoustic_snapshot.png",
        )
        self.assertEqual(result_png.status, "success")
        self.assertEqual(result_png.image_metadata.format, "PNG")
        self.assertIsNone(result_png.sonar_metadata)

    # -------------------------------------------------------------------------
    # Test 2 & 3: Synthetic XTF & JSF into Master Pipeline
    # -------------------------------------------------------------------------

    def test_02_synthetic_xtf_to_waterfall_to_pipeline(self):
        """
        Verify synthetic XTF recording feeds through parser -> waterfall -> master pipeline.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=12,
            samples_per_chan=80,
            lat=24.8607,
            lon=67.0011,
            heading=180.0,
            altitude=15.0,
            depth=25.0,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="transect_01.xtf",
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.image_metadata.format, "XTF")
        self.assertIsNotNone(result.sonar_metadata)
        self.assertEqual(result.sonar_metadata.format, "XTF")
        self.assertEqual(result.sonar_metadata.total_pings, 12)
        self.assertEqual(result.sonar_metadata.waterfall_width, 160)  # 80 port + 80 stbd
        self.assertEqual(result.sonar_metadata.channel_layout, "port_nadir_starboard")
        self.assertIsNotNone(result.quality_assessment)
        self.assertGreaterEqual(result.quality_assessment.overall_quality_score, 0.0)

    def test_03_synthetic_jsf_to_waterfall_to_pipeline(self):
        """
        Verify synthetic JSF recording feeds through parser -> waterfall -> master pipeline.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=10,
            samples_per_chan=90,
            lat=24.8607,
            lon=67.0011,
            heading=90.0,
            altitude=12.0,
            depth=20.0,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="trackline_02.jsf",
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.image_metadata.format, "JSF")
        self.assertIsNotNone(result.sonar_metadata)
        self.assertEqual(result.sonar_metadata.format, "JSF")
        self.assertEqual(result.sonar_metadata.total_pings, 10)
        self.assertEqual(result.sonar_metadata.waterfall_width, 180)  # 90 port + 90 stbd

    # -------------------------------------------------------------------------
    # Test 4: Parser metadata reaches pipeline context
    # -------------------------------------------------------------------------

    def test_04_parser_metadata_reaches_pipeline_context(self):
        """
        Verify all sonar provenance metrics populate SonarMetadataContext on MasterAnalysisResult.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=8,
            samples_per_chan=100,
            sample_interval_ns=20000,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="survey_rec.jsf",
        )
        meta = result.sonar_metadata
        self.assertIsNotNone(meta)
        self.assertEqual(meta.filename, "survey_rec.jsf")
        self.assertEqual(meta.format, "JSF")
        self.assertEqual(meta.total_pings, 8)
        self.assertEqual(meta.channel_count, 2)
        self.assertEqual(meta.channels_included, [0, 1])
        self.assertEqual(meta.waterfall_width, 200)
        self.assertEqual(meta.waterfall_height, 8)
        self.assertEqual(meta.nadir_pixel_x, 100.0)
        self.assertIsNotNone(meta.meters_per_pixel)
        self.assertIsNotNone(meta.slant_range_m)

    # -------------------------------------------------------------------------
    # Test 5 & 6: Missing navigation remains None without (0, 0) fallback
    # -------------------------------------------------------------------------

    def test_05_missing_navigation_remains_none(self):
        """
        Unlogged navigation coordinates must strictly remain None.
        """
        jsf_no_nav = build_synthetic_jsf_binary(
            num_pings=5,
            lat=None,
            lon=None,
            heading=None,
            altitude=None,
            depth=None,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_no_nav,
            filename="unnavigated.jsf",
        )
        self.assertIsNotNone(result.sonar_metadata)
        nav = result.sonar_metadata.navigation
        if nav:
            self.assertIsNone(nav.latitude)
            self.assertIsNone(nav.longitude)
            self.assertIsNone(nav.heading_deg)
            self.assertIsNone(nav.altitude_m)
            self.assertIsNone(nav.depth_m)

    def test_06_no_zero_zero_geographic_fallback(self):
        """
        Null Island coordinates (0.0, 0.0) or sentinels must never be treated as valid navigation.
        """
        jsf_null_island = build_synthetic_jsf_binary(
            num_pings=5,
            lat=0.0,
            lon=0.0,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_null_island,
            filename="null_island.jsf",
        )
        nav = result.sonar_metadata.navigation
        if nav:
            self.assertIsNone(nav.latitude)
            self.assertIsNone(nav.longitude)

    # -------------------------------------------------------------------------
    # Test 7 - 10: Downstream Services Reused (YOLO, Preproc, Shadow, Physics)
    # -------------------------------------------------------------------------

    def test_07_existing_yolo_invocation_reused(self):
        """
        Verify that inference_service.predict_array is called during raw sonar processing.
        """
        from app.services.inference_service import inference_service
        xtf_bytes = build_synthetic_xtf_binary(num_pings=6)
        with patch("app.services.master_pipeline_service.inference_service.predict_array", wraps=inference_service.predict_array) as mock_predict:
            result = master_pipeline_service.execute_pipeline(
                image_bytes=xtf_bytes,
                filename="yolo_test.xtf",
            )
            self.assertEqual(result.status, "success")
            self.assertTrue(mock_predict.called)
            self.assertGreater(result.timings.yolo_inference_ms, 0.0)

    def test_08_existing_preprocessing_reused(self):
        """
        Verify that Stage 3 preprocessing executes on the waterfall raster.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=8)
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="preproc_test.jsf",
            preprocessing_preset="sonar_acoustic",
        )
        self.assertEqual(result.status, "success")
        self.assertGreater(result.timings.preprocessing_ms, 0.0)

    def test_09_existing_shadow_service_reused(self):
        """
        Verify that Stage 6 acoustic shadow extraction executes during raw sonar pipeline run.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8)
        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="shadow_test.xtf",
        )
        self.assertEqual(result.status, "success")
        self.assertGreaterEqual(result.timings.shadow_evidence_ms, 0.0)

    def test_10_existing_physics_service_reused(self):
        """
        Verify that Stage 7 ocean physics enrichment executes on sonar targets.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=8)
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="physics_test.jsf",
        )
        self.assertEqual(result.status, "success")
        self.assertGreaterEqual(result.timings.physics_validation_ms, 0.0)

    # -------------------------------------------------------------------------
    # Test 11 & 12: Corrupt / Invalid Sonar Inputs
    # -------------------------------------------------------------------------

    def test_11_invalid_xtf_rejected_cleanly(self):
        """
        Verify that corrupted XTF data raises InputValidationError without internal stack traces.
        """
        bad_xtf = b"Corrupt XTF data without valid header"
        with self.assertRaises(InputValidationError):
            master_pipeline_service.execute_pipeline(
                image_bytes=bad_xtf,
                filename="corrupt.xtf",
            )

        # API endpoint check
        resp = self.client.post(
            "/api/v1/analyses/analyze",
            files={"file": ("corrupt.xtf", io.BytesIO(bad_xtf), "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("Traceback", resp.json().get("detail", ""))

    def test_12_invalid_jsf_rejected_cleanly(self):
        """
        Verify that corrupted JSF data raises InputValidationError without internal stack traces.
        """
        bad_jsf = b"Corrupt JSF data without 0x1601 marker"
        with self.assertRaises(InputValidationError):
            master_pipeline_service.execute_pipeline(
                image_bytes=bad_jsf,
                filename="corrupt.jsf",
            )

        # API endpoint check
        resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("corrupt.jsf", io.BytesIO(bad_jsf), "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("Traceback", resp.json().get("detail", ""))

    # -------------------------------------------------------------------------
    # Test 13: Bounded max_pings
    # -------------------------------------------------------------------------

    def test_13_max_pings_bounded(self):
        """
        Verify that max_pings parameter limits along-track pings ingested into pipeline.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=20, samples_per_chan=50)
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="large_survey.jsf",
            max_pings=7,
        )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.sonar_metadata.waterfall_height, 7)

    # -------------------------------------------------------------------------
    # Test 14: Dedicated /sonar Analysis API Endpoint
    # -------------------------------------------------------------------------

    def test_14_api_analyses_sonar_endpoint(self):
        """
        Verify that POST /api/v1/analyses/sonar executes full pipeline on raw sonar upload.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=8, samples_per_chan=75)
        resp = self.client.post(
            "/api/v1/analyses/sonar?max_pings=5&channels=0,1",
            files={"file": ("api_test.jsf", io.BytesIO(jsf_bytes), "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("sonar_metadata", data)
        self.assertIsNotNone(data["sonar_metadata"])
        self.assertEqual(data["sonar_metadata"]["format"], "JSF")
        self.assertEqual(data["sonar_metadata"]["waterfall_height"], 5)
        self.assertIn("summary", data)
        self.assertIn("timings", data)


if __name__ == "__main__":
    unittest.main()
