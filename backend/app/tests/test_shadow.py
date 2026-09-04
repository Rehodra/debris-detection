"""
Unit and integration tests for Acoustic Shadow Service and API endpoints.
Tests candidate extraction, spatial vectors, directional acoustic alignment,
extent geometry, hydrographic height estimation, and composite shadow scoring.
"""

import io
import unittest
import numpy as np
import cv2
from PIL import Image
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.schemas.detection import BoundingBox
    from app.services.shadow_service import shadow_service
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.schemas.detection import BoundingBox
    from backend.app.services.shadow_service import shadow_service


class TestShadowService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_synthetic_sonar_target(self) -> Tuple[np.ndarray, BoundingBox]:
        """
        Creates a synthetic sonar image (500x500) with background intensity ~70,
        a bright highlight at (150, 200) to (210, 260) with intensity 230,
        and an acoustic shadow directly trailing to the right (210, 200) to (310, 260) with intensity 10.
        """
        img = np.full((500, 500), 70, dtype=np.uint8)

        # Highlight (acoustic reflection)
        cv2.rectangle(img, (150, 200), (210, 260), 230, -1)

        # Shadow (acoustic void)
        cv2.rectangle(img, (210, 200), (310, 260), 10, -1)

        bbox = BoundingBox(
            x_min=150.0,
            y_min=200.0,
            x_max=210.0,
            y_max=260.0,
            width=60.0,
            height=60.0,
            normalized_x_min=0.30,
            normalized_y_min=0.40,
            normalized_x_max=0.42,
            normalized_y_max=0.52,
        )
        return img, bbox

    def _create_synthetic_jpeg_bytes(self) -> bytes:
        img, _ = self._create_synthetic_sonar_target()
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def test_candidate_extraction(self):
        img, bbox = self._create_synthetic_sonar_target()
        candidates = shadow_service.extract_shadow_candidates(img, bbox)
        self.assertGreater(len(candidates), 0)

        # Check candidate parameters
        cnt, (bx, by, bw, bh), mean_int, area, ambient_med = candidates[0]
        self.assertLess(mean_int, 25.0)  # Dark shadow
        self.assertGreaterEqual(area, 500.0)  # Substantial shadow region
        self.assertGreaterEqual(bx, 200)  # Positioned right of highlight

    def test_spatial_relationship_and_adjacency(self):
        img, bbox = self._create_synthetic_sonar_target()
        candidates = shadow_service.extract_shadow_candidates(img, bbox)
        cnt, bbox_tuple, _, _, _ = candidates[0]

        spatial = shadow_service.analyze_spatial_relationship(bbox, bbox_tuple, cnt)
        self.assertTrue(spatial.is_adjacent)
        self.assertGreater(spatial.offset_dx, 0.0)  # Offset to the right
        self.assertLessEqual(spatial.boundary_gap_pixels, 5.0)  # Touching boundary

    def test_direction_analysis_and_nadir_alignment(self):
        img, bbox = self._create_synthetic_sonar_target()
        candidates = shadow_service.extract_shadow_candidates(img, bbox)
        cnt, bbox_tuple, _, _, _ = candidates[0]
        spatial = shadow_service.analyze_spatial_relationship(bbox, bbox_tuple, cnt)

        # Highlight is at x ~ 180, shadow is at x ~ 260
        # If nadir is at x = 100, target is on starboard -> shadow should cast East (0 deg)
        direction = shadow_service.analyze_direction(spatial, nadir_x=100.0)
        self.assertEqual(direction.cardinal_direction, "E")
        self.assertAlmostEqual(direction.angle_degrees, 0.0, delta=5.0)
        self.assertAlmostEqual(direction.direction_alignment_score, 1.0, delta=0.05)

        # If nadir was at x = 400 (target is port side), sound radiates leftward,
        # but shadow casts rightward -> alignment score should be 0.0
        opp_direction = shadow_service.analyze_direction(spatial, nadir_x=400.0)
        self.assertAlmostEqual(opp_direction.direction_alignment_score, 0.0, delta=0.05)

    def test_extent_and_hydrographic_height_formula(self):
        img, bbox = self._create_synthetic_sonar_target()
        candidates = shadow_service.extract_shadow_candidates(img, bbox)
        cnt, bbox_tuple, _, _, _ = candidates[0]
        spatial = shadow_service.analyze_spatial_relationship(bbox, bbox_tuple, cnt)
        direction = shadow_service.analyze_direction(spatial, nadir_x=100.0)

        # Shadow length is 100px. At 0.05 m/px: length = 5.0m
        # With Altitude = 10.0m, Slant Range = 30.0m:
        # h = (5.0 * 10.0) / (30.0 + 5.0) = 50 / 35 = 1.43m
        extent = shadow_service.measure_extent(
            shadow_contour=cnt,
            shadow_direction=direction,
            meters_per_pixel=0.05,
            sensor_altitude_m=10.0,
            slant_range_m=30.0,
        )
        self.assertAlmostEqual(extent.length_pixels, 100.0, delta=5.0)
        self.assertIsNotNone(extent.estimated_object_height_m)
        self.assertAlmostEqual(extent.estimated_object_height_m, 1.43, delta=0.1)

    def test_composite_shadow_score(self):
        img, bbox = self._create_synthetic_sonar_target()
        result = shadow_service.analyze_detection_shadow(
            image_gray=img,
            detection_id="det_123",
            class_name="shipwreck",
            bbox=bbox,
            nadir_x=100.0,
            meters_per_pixel=0.05,
            sensor_altitude_m=10.0,
            slant_range_m=30.0,
        )
        self.assertTrue(result.has_shadow)
        self.assertGreaterEqual(result.shadow_score, 0.85)
        self.assertEqual(result.quality_assessment, "Strong Shadow - High Physical Confidence")
        self.assertGreater(result.confidence_adjustment, 0.0)

    def test_shadowless_anomaly_scoring(self):
        # A flat bright patch with no shadow
        img = np.full((500, 500), 70, dtype=np.uint8)
        cv2.rectangle(img, (200, 200), (250, 250), 220, -1)

        bbox = BoundingBox(
            x_min=200.0, y_min=200.0, x_max=250.0, y_max=250.0,
            width=50.0, height=50.0,
            normalized_x_min=0.4, normalized_y_min=0.4,
            normalized_x_max=0.5, normalized_y_max=0.5,
        )
        result = shadow_service.analyze_detection_shadow(
            image_gray=img,
            detection_id="det_flat",
            class_name="other",
            bbox=bbox,
        )
        self.assertFalse(result.has_shadow)
        self.assertEqual(result.shadow_score, 0.0)
        self.assertLess(result.confidence_adjustment, 0.0)

    def test_render_shadow_overlay(self):
        img, bbox = self._create_synthetic_sonar_target()
        img_bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        result = shadow_service.analyze_detection_shadow(
            image_gray=img,
            detection_id="det_123",
            class_name="shipwreck",
            bbox=bbox,
            meters_per_pixel=0.05,
            sensor_altitude_m=10.0,
            slant_range_m=30.0,
        )
        rendered = shadow_service.render_shadow_overlay(img_bgr, [result])
        self.assertEqual(rendered.shape, img_bgr.shape)
        # Rendered image should have modified pixel values from cyan polygons / yellow arrows
        self.assertFalse(np.array_equal(rendered, img_bgr))

    def test_api_shadows_analyze_endpoint(self):
        jpeg_bytes = self._create_synthetic_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/shadows/analyze?confidence_threshold=0.10&nadir_x=100",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_detections_analyzed", data)
        self.assertIn("shadows_confirmed", data)
        self.assertIn("average_shadow_score", data)
        self.assertIn("results", data)

    def test_api_shadows_visualize_endpoint(self):
        jpeg_bytes = self._create_synthetic_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/shadows/visualize?confidence_threshold=0.10",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertIn("X-Shadows-Confirmed", response.headers)
        self.assertGreater(len(response.content), 0)


if __name__ == "__main__":
    unittest.main()
