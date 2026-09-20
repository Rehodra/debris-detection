"""
Unit and integration tests for Phase 6A: Unified Sonar Analysis Backend Contract.

Validates:
1. SonarAnalysisResponse contract for raw XTF recordings.
2. SonarAnalysisResponse contract for raw JSF recordings.
3. Backward compatibility for standard marine imagery (PNG/JPEG) with no fake sonar metadata.
4. Missing navigation handling (strictly None, no Null Island / 0,0 sentinels).
5. Coordinate convention and metadata consistency (top-left origin, across-track X, along-track Y).
6. Lightweight waterfall handling (no embedded base64 waterfall in default JSON response, raster reference provided).
7. Full Pydantic JSON serialization round-trip.
8. FastAPI endpoint POST /api/v1/analyses/sonar returning SonarAnalysisResponse with dual-layer compatibility.
"""

import io
import json
import unittest
from typing import Dict, Any

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import (
    SonarAnalysisResponse,
    AnalysisSourceInfo,
    SonarRasterMetadata,
    MasterAnalysisResult,
)
from app.schemas.sonar import SonarNavigation
from app.services.master_pipeline_service import master_pipeline_service
from app.tests.test_xtf_parser import build_synthetic_xtf_binary
from app.tests.test_jsf_parser import build_synthetic_jsf_binary


class TestSonarAnalysisContract(unittest.TestCase):
    """
    Test suite validating the Unified Sonar Analysis Response Contract (Phase 6A).
    """

    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_png_bytes(self, width: int = 100, height: int = 100) -> bytes:
        img = np.full((height, width, 3), 75, dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (60, 60), (220, 220, 220), -1)
        _, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    def _create_sample_jpeg_bytes(self, width: int = 100, height: int = 100) -> bytes:
        img = np.full((height, width, 3), 85, dtype=np.uint8)
        cv2.circle(img, (50, 50), 20, (200, 200, 200), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    # -------------------------------------------------------------------------
    # Test 1: XTF input produces unified contract
    # -------------------------------------------------------------------------
    def test_01_xtf_unified_contract(self):
        """
        Verify that XTF input correctly populates source, sonar, navigation,
        analysis, and warnings in SonarAnalysisResponse.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=10,
            samples_per_chan=64,
            lat=25.1234,
            lon=66.5678,
            heading=135.0,
            altitude=15.0,
            depth=6.0,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="survey_run_01.xtf",
            return_visualization=False,
        )
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="survey_run_01.xtf", file_size_bytes=len(xtf_bytes)
        )

        # Source
        self.assertEqual(response.status, "success")
        self.assertEqual(response.source.format, "XTF")
        self.assertEqual(response.source.filename, "survey_run_01.xtf")
        self.assertEqual(response.source.file_size, len(xtf_bytes))

        # Sonar / Raster metadata
        self.assertIsNotNone(response.sonar)
        self.assertEqual(response.sonar.total_pings, 10)
        self.assertGreaterEqual(response.sonar.channel_count, 1)
        self.assertGreater(response.sonar.waterfall_width, 0)
        self.assertEqual(response.sonar.waterfall_height, 10)
        self.assertIsNotNone(response.sonar.nadir_pixel)
        self.assertIsNotNone(response.sonar.meters_per_pixel)
        self.assertEqual(response.sonar.raster_reference, f"/api/v1/analyses/{response.mission_id}/sonar/raster")
        self.assertEqual(response.sonar.coordinate_convention, "top_left_origin_x_across_y_along")

        # Navigation
        self.assertIsNotNone(response.navigation)
        self.assertAlmostEqual(response.navigation.latitude, 25.1234, places=4)
        self.assertAlmostEqual(response.navigation.longitude, 66.5678, places=4)
        self.assertAlmostEqual(response.navigation.heading, 135.0, places=1)
        self.assertAlmostEqual(response.navigation.altitude, 15.0, places=1)
        self.assertAlmostEqual(response.navigation.depth, 6.0, places=1)

        # Analysis
        self.assertIsNotNone(response.analysis)
        self.assertIsInstance(response.analysis, MasterAnalysisResult)
        self.assertIsNotNone(response.analysis.summary)
        self.assertIsNotNone(response.analysis.timings)
        self.assertIsNotNone(response.analysis.quality_assessment)
        self.assertIsInstance(response.analysis.targets, list)

        # Warnings list
        self.assertIsInstance(response.warnings, list)

    # -------------------------------------------------------------------------
    # Test 2: JSF input produces unified contract
    # -------------------------------------------------------------------------
    def test_02_jsf_unified_contract(self):
        """
        Verify that JSF input correctly populates source, sonar, navigation,
        analysis, and warnings in SonarAnalysisResponse.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=8,
            samples_per_chan=50,
            lat=24.8600,
            lon=67.0010,
            heading=45.0,
            altitude=12.0,
            depth=4.5,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="coastal_survey.jsf",
            return_visualization=False,
        )
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="coastal_survey.jsf", file_size_bytes=len(jsf_bytes)
        )

        self.assertEqual(response.status, "success")
        self.assertEqual(response.source.format, "JSF")
        self.assertEqual(response.source.filename, "coastal_survey.jsf")
        self.assertEqual(response.source.file_size, len(jsf_bytes))

        self.assertIsNotNone(response.sonar)
        self.assertEqual(response.sonar.total_pings, 8)
        self.assertEqual(response.sonar.waterfall_height, 8)
        self.assertIsNotNone(response.sonar.nadir_pixel)
        self.assertEqual(response.sonar.raster_reference, f"/api/v1/analyses/{response.mission_id}/sonar/raster")

        self.assertIsNotNone(response.navigation)
        self.assertAlmostEqual(response.navigation.latitude, 24.8600, places=4)
        self.assertAlmostEqual(response.navigation.longitude, 67.0010, places=4)
        self.assertAlmostEqual(response.navigation.heading, 45.0, places=1)
        self.assertAlmostEqual(response.navigation.altitude, 12.0, places=1)
        self.assertAlmostEqual(response.navigation.depth, 4.5, places=1)

    # -------------------------------------------------------------------------
    # Test 3: Standard image compatibility (PNG & JPG)
    # -------------------------------------------------------------------------
    def test_03_standard_image_compatibility(self):
        """
        Standard images (PNG, JPEG) must proceed through the existing pipeline,
        and SonarAnalysisResponse must NOT fabricate sonar or navigation metadata.
        """
        png_bytes = self._create_sample_png_bytes()
        result_png = master_pipeline_service.execute_pipeline(
            image_bytes=png_bytes,
            filename="optical_sonar.png",
        )
        response_png = SonarAnalysisResponse.from_analysis_result(
            result_png, filename="optical_sonar.png", file_size_bytes=len(png_bytes)
        )

        self.assertEqual(response_png.status, "success")
        self.assertEqual(response_png.source.format, "PNG")
        self.assertEqual(response_png.source.filename, "optical_sonar.png")
        self.assertIsNone(response_png.sonar, "Standard image must have sonar=None")
        self.assertIsNone(response_png.navigation, "Standard image must have navigation=None")
        self.assertIsNotNone(response_png.analysis)
        self.assertEqual(response_png.analysis.image_metadata.format, "PNG")

        jpeg_bytes = self._create_sample_jpeg_bytes()
        result_jpeg = master_pipeline_service.execute_pipeline(
            image_bytes=jpeg_bytes,
            filename="mosaic.jpg",
        )
        response_jpeg = SonarAnalysisResponse.from_analysis_result(
            result_jpeg, filename="mosaic.jpg", file_size_bytes=len(jpeg_bytes)
        )
        self.assertEqual(response_jpeg.source.format, "JPEG")
        self.assertIsNone(response_jpeg.sonar)
        self.assertIsNone(response_jpeg.navigation)

    # -------------------------------------------------------------------------
    # Test 4: Missing navigation strictly remains None
    # -------------------------------------------------------------------------
    def test_04_missing_navigation_strictly_none(self):
        """
        Raw sonar recordings without valid GPS or telemetry must leave navigation
        fields strictly None without fallback to (0,0) or fabricated values.
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
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="unnavigated.jsf", file_size_bytes=len(jsf_no_nav)
        )

        # Navigation must be None or all its individual coordinates None
        if response.navigation is not None:
            self.assertIsNone(response.navigation.latitude)
            self.assertIsNone(response.navigation.longitude)
            self.assertIsNone(response.navigation.heading)
            self.assertIsNone(response.navigation.altitude)
            self.assertIsNone(response.navigation.depth)
        else:
            self.assertIsNone(response.navigation)

    # -------------------------------------------------------------------------
    # Test 5: Coordinate metadata consistency
    # -------------------------------------------------------------------------
    def test_05_coordinate_metadata_consistency(self):
        """
        Verify that waterfall_width, waterfall_height, nadir_pixel, and meters_per_pixel
        are internally consistent with the underlying raster.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=14,
            samples_per_chan=80,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="consistency_test.xtf",
        )
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="consistency_test.xtf", file_size_bytes=len(xtf_bytes)
        )

        sonar = response.sonar
        self.assertIsNotNone(sonar)
        self.assertEqual(sonar.waterfall_height, 14)
        self.assertGreater(sonar.waterfall_width, 0)
        # Nadir pixel is across-track center
        self.assertGreater(sonar.nadir_pixel, 0.0)
        self.assertLess(sonar.nadir_pixel, float(sonar.waterfall_width))
        self.assertGreater(sonar.meters_per_pixel, 0.0)
        self.assertEqual(sonar.coordinate_convention, "top_left_origin_x_across_y_along")

    # -------------------------------------------------------------------------
    # Test 6: Lightweight waterfall handling (No embedded base64 raster)
    # -------------------------------------------------------------------------
    def test_06_no_embedded_waterfall_in_response(self):
        """
        Verify that the response JSON does not embed a heavy base64 waterfall image
        when return_visualization=False (the default for the sonar endpoint).
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=10, samples_per_chan=100)
        result = master_pipeline_service.execute_pipeline(
            image_bytes=jsf_bytes,
            filename="lightweight_test.jsf",
            return_visualization=False,
        )
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="lightweight_test.jsf", file_size_bytes=len(jsf_bytes)
        )

        # annotated_image_base64 must be None
        self.assertIsNone(response.analysis.annotated_image_base64)

        # Serialized JSON should be compact (< 50 KB)
        json_str = response.model_dump_json()
        self.assertLess(len(json_str), 50000, "Response JSON must be lightweight and under 50KB")

        # Raster reference endpoint is explicitly provided
        self.assertEqual(response.sonar.raster_reference, f"/api/v1/analyses/{response.mission_id}/sonar/raster")

    # -------------------------------------------------------------------------
    # Test 7: Pydantic response JSON serialization round-trip
    # -------------------------------------------------------------------------
    def test_07_pydantic_serialization_roundtrip(self):
        """
        Verify that SonarAnalysisResponse serializes to valid JSON and deserializes cleanly.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=6,
            samples_per_chan=50,
            lat=24.1,
            lon=67.2,
            heading=90.0,
            altitude=10.0,
            depth=2.0,
        )
        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="roundtrip.xtf",
            return_visualization=False,
        )
        response = SonarAnalysisResponse.from_analysis_result(
            result, filename="roundtrip.xtf", file_size_bytes=len(xtf_bytes)
        )

        # Dump to JSON
        json_str = response.model_dump_json()
        parsed_dict = json.loads(json_str)

        self.assertIn("source", parsed_dict)
        self.assertIn("sonar", parsed_dict)
        self.assertIn("navigation", parsed_dict)
        self.assertIn("analysis", parsed_dict)
        self.assertIn("warnings", parsed_dict)

        # Deserialize back
        reloaded = SonarAnalysisResponse.model_validate_json(json_str)
        self.assertEqual(reloaded.source.format, "XTF")
        self.assertEqual(reloaded.sonar.total_pings, 6)
        self.assertAlmostEqual(reloaded.navigation.latitude, 24.1, places=3)
        self.assertAlmostEqual(reloaded.navigation.heading, 90.0, places=1)

    # -------------------------------------------------------------------------
    # Test 8: Dedicated POST /api/v1/analyses/sonar API Endpoint
    # -------------------------------------------------------------------------
    def test_08_api_analyses_sonar_endpoint_contract(self):
        """
        Verify that POST /api/v1/analyses/sonar returns SonarAnalysisResponse schema
        with both the new structured contract and legacy top-level keys.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=8,
            samples_per_chan=60,
            lat=24.86,
            lon=67.00,
            heading=180.0,
            altitude=15.0,
            depth=5.0,
        )
        resp = self.client.post(
            "/api/v1/analyses/sonar?max_pings=6",
            files={"file": ("contract_test.jsf", io.BytesIO(jsf_bytes), "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Phase 6A Contract Keys:
        self.assertIn("source", data)
        self.assertEqual(data["source"]["format"], "JSF")
        self.assertEqual(data["source"]["filename"], "contract_test.jsf")
        self.assertEqual(data["source"]["file_size"], len(jsf_bytes))

        self.assertIn("sonar", data)
        self.assertEqual(data["sonar"]["waterfall_height"], 6)
        self.assertIsNotNone(data["sonar"]["nadir_pixel"])
        self.assertEqual(data["sonar"]["raster_reference"], f"/api/v1/analyses/{data['mission_id']}/sonar/raster")
        self.assertEqual(data["sonar"]["coordinate_convention"], "top_left_origin_x_across_y_along")

        self.assertIn("navigation", data)
        self.assertIsNotNone(data["navigation"])
        self.assertAlmostEqual(data["navigation"]["latitude"], 24.86, places=2)
        self.assertAlmostEqual(data["navigation"]["heading"], 180.0, places=1)
        self.assertAlmostEqual(data["navigation"]["altitude"], 15.0, places=1)
        self.assertAlmostEqual(data["navigation"]["depth"], 5.0, places=1)

        self.assertIn("analysis", data)
        self.assertIn("summary", data["analysis"])
        self.assertIn("timings", data["analysis"])
        self.assertIn("targets", data["analysis"])
        self.assertIsNone(data["analysis"]["annotated_image_base64"])

        # Backward compatibility top-level keys:
        self.assertEqual(data["status"], "success")
        self.assertIn("sonar_metadata", data)
        self.assertIn("summary", data)
        self.assertIn("timings", data)
        self.assertIn("targets", data)

    # -------------------------------------------------------------------------
    # Test 9: Optional visualization flag on API endpoint
    # -------------------------------------------------------------------------
    def test_09_api_optional_visualization(self):
        """
        Verify that callers can optionally request annotated base64 overlay
        via return_visualization=true query parameter.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=5, samples_per_chan=50)
        resp = self.client.post(
            "/api/v1/analyses/sonar?return_visualization=true",
            files={"file": ("vis_test.jsf", io.BytesIO(jsf_bytes), "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # When explicitly requested, annotated_image_base64 is populated
        self.assertIsNotNone(data["analysis"]["annotated_image_base64"])


if __name__ == "__main__":
    unittest.main()
