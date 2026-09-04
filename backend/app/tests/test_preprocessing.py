"""Unit and integration tests for the Sonar & Marine Debris Preprocessing Service."""

import io
import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.services.preprocessing_service import preprocessing_service
    from app.schemas.preprocessing import (
        PreprocessingConfig,
        PreprocessingPreset,
        ColormapType,
    )
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.services.preprocessing_service import preprocessing_service
    from backend.app.schemas.preprocessing import (
        PreprocessingConfig,
        PreprocessingPreset,
        ColormapType,
    )


class TestPreprocessingService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_sonar_image(self, width: int = 500, height: int = 300) -> np.ndarray:
        """Create synthetic low-contrast sonar image with noise and highlight-shadow debris pair."""
        np.random.seed(42)
        base = np.random.randint(50, 90, (height, width, 3), dtype=np.uint8)
        # Highlight (reflective debris target)
        cv2.rectangle(base, (100, 100), (180, 200), (230, 230, 230), -1)
        # Acoustic shadow (dark sound blockage)
        cv2.rectangle(base, (180, 100), (280, 200), (15, 15, 15), -1)
        return base

    def _encode_to_jpeg_bytes(self, img: np.ndarray) -> bytes:
        success, encoded = cv2.imencode(".jpg", img)
        return encoded.tobytes()

    # -------------------------------------------------------------------------
    # Core Filter Unit Tests
    # -------------------------------------------------------------------------

    def test_denoise_methods(self):
        img = self._create_sample_sonar_image()
        # Bilateral
        denoised_bi = preprocessing_service.denoise(img, method="bilateral", strength=7)
        self.assertEqual(denoised_bi.shape, img.shape)
        # Median
        denoised_med = preprocessing_service.denoise(img, method="median", strength=5)
        self.assertEqual(denoised_med.shape, img.shape)
        # Gaussian
        denoised_gauss = preprocessing_service.denoise(img, method="gaussian", strength=5)
        self.assertEqual(denoised_gauss.shape, img.shape)

    def test_clahe_contrast_enhancement(self):
        img = self._create_sample_sonar_image()
        enhanced = preprocessing_service.apply_clahe(img, clip_limit=3.0, tile_grid_size=8)
        self.assertEqual(enhanced.shape, img.shape)
        # Compare dynamic range
        stats_before = preprocessing_service.compute_image_stats(img)
        stats_after = preprocessing_service.compute_image_stats(enhanced)
        self.assertGreaterEqual(stats_after.dynamic_range, stats_before.dynamic_range)

    def test_gamma_adjustment(self):
        img = self._create_sample_sonar_image()
        brighter = preprocessing_service.adjust_gamma(img, gamma=0.5)
        darker = preprocessing_service.adjust_gamma(img, gamma=2.0)
        self.assertGreater(np.mean(brighter), np.mean(img))
        self.assertLess(np.mean(darker), np.mean(img))

    def test_sharpening(self):
        img = self._create_sample_sonar_image()
        sharpened = preprocessing_service.sharpen(img, amount=1.5)
        self.assertEqual(sharpened.shape, img.shape)
        # Edge differences should exist
        diff = cv2.absdiff(img, sharpened)
        self.assertGreater(np.sum(diff), 0)

    def test_colormap_application(self):
        # Grayscale input
        gray = np.linspace(0, 255, 10000, dtype=np.uint8).reshape((100, 100))
        amber = preprocessing_service.apply_colormap(gray, ColormapType.AMBER)
        self.assertEqual(amber.shape, (100, 100, 3))

        inferno = preprocessing_service.apply_colormap(gray, ColormapType.INFERNO)
        self.assertEqual(inferno.shape, (100, 100, 3))

    def test_letterbox_resize(self):
        img = np.zeros((200, 400, 3), dtype=np.uint8)
        padded = preprocessing_service.letterbox_resize(img, target_width=640, target_height=640)
        self.assertEqual(padded.shape, (640, 640, 3))

    def test_presets_processing(self):
        img = self._create_sample_sonar_image()
        for preset in [
            PreprocessingPreset.BALANCED,
            PreprocessingPreset.SONAR_ACOUSTIC,
            PreprocessingPreset.TURBID_WATER,
            PreprocessingPreset.EDGE_ENHANCE,
            PreprocessingPreset.RAW_NORMALIZE,
            PreprocessingPreset.FAST,
        ]:
            cfg = PreprocessingConfig(preset=preset)
            processed, resp = preprocessing_service.process_image(img, config=cfg)
            self.assertEqual(resp.status, "success")
            self.assertGreater(len(resp.applied_steps), 0 if preset != PreprocessingPreset.RAW_NORMALIZE else -1)
            self.assertEqual(processed.shape[:2], img.shape[:2])

    # -------------------------------------------------------------------------
    # API Integration Tests
    # -------------------------------------------------------------------------

    def test_api_list_presets(self):
        res = self.client.get(f"{settings.API_V1_STR}/preprocessing/presets")
        self.assertEqual(res.status_code, 200)
        presets = res.json()
        self.assertGreaterEqual(len(presets), 5)
        preset_names = [p["preset"] for p in presets]
        self.assertIn("balanced", preset_names)
        self.assertIn("sonar_acoustic", preset_names)
        self.assertIn("turbid_water", preset_names)

    def test_api_process_image_endpoint(self):
        img = self._create_sample_sonar_image()
        jpeg_bytes = self._encode_to_jpeg_bytes(img)
        files = {"file": ("sonar_scan.jpg", jpeg_bytes, "image/jpeg")}
        res = self.client.post(
            f"{settings.API_V1_STR}/preprocessing/process?preset=sonar_acoustic&return_base64=true",
            files=files,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("applied_steps", data)
        self.assertIn("input_stats", data)
        self.assertIn("output_stats", data)
        self.assertIsNotNone(data["processed_image_base64"])
        self.assertTrue(data["processed_image_base64"].startswith("data:image/jpeg;base64,"))

    def test_api_preview_endpoint(self):
        img = self._create_sample_sonar_image()
        jpeg_bytes = self._encode_to_jpeg_bytes(img)
        files = {"file": ("sonar_scan.jpg", jpeg_bytes, "image/jpeg")}
        res = self.client.post(
            f"{settings.API_V1_STR}/preprocessing/preview?preset=turbid_water",
            files=files,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/jpeg")
        self.assertGreater(len(res.content), 0)

    def test_api_process_with_custom_sizing_and_colormap(self):
        img = self._create_sample_sonar_image(300, 200)
        jpeg_bytes = self._encode_to_jpeg_bytes(img)
        files = {"file": ("sonar_scan.jpg", jpeg_bytes, "image/jpeg")}
        res = self.client.post(
            f"{settings.API_V1_STR}/preprocessing/process?target_width=640&target_height=640&colormap=amber",
            files=files,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["output_dimensions"], [640, 640])

    def test_api_process_empty_file_fails(self):
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        res = self.client.post(f"{settings.API_V1_STR}/preprocessing/process", files=files)
        self.assertEqual(res.status_code, 400)

    def test_inference_with_preprocessing_integration(self):
        img = self._create_sample_sonar_image(640, 640)
        jpeg_bytes = self._encode_to_jpeg_bytes(img)
        files = {"file": ("sonar_scan.jpg", jpeg_bytes, "image/jpeg")}
        res = self.client.post(
            f"{settings.API_V1_STR}/detections/predict?confidence_threshold=0.25&preprocessing_preset=sonar_acoustic",
            files=files,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("detections", data)


if __name__ == "__main__":
    unittest.main()
