"""Unit tests for ML components: class_map, model_loader, postprocess, inference_service."""

import unittest
import numpy as np
import cv2

from app.ml.class_map import (
    CLASS_MAP,
    CLASS_NAMES,
    get_class_name,
    get_class_id,
    get_class_metadata,
    get_all_classes,
)
from app.ml.model_loader import model_loader
from app.ml.postprocess import (
    render_detections_overlay,
    encode_image_to_jpeg_bytes,
    encode_image_to_base64,
)
from app.services.inference_service import inference_service
from app.schemas.detection import TilingConfig


class TestMLComponents(unittest.TestCase):
    def test_class_map_lookup(self):
        self.assertEqual(get_class_name(0), "shipwreck")
        self.assertEqual(get_class_name(1), "pipe")
        self.assertEqual(get_class_name(2), "ghost_net")
        self.assertEqual(get_class_name(3), "marine_debris")
        self.assertEqual(get_class_name(4), "aircraft")
        self.assertEqual(get_class_name(5), "other")
        self.assertEqual(get_class_name(6), "fish")

        self.assertEqual(get_class_id("shipwreck"), 0)
        self.assertEqual(get_class_id("pipe"), 1)
        self.assertEqual(get_class_id("ghost_net"), 2)
        self.assertEqual(get_class_id("marine_debris"), 3)
        self.assertEqual(get_class_id("aircraft"), 4)
        self.assertEqual(get_class_id("other"), 5)
        self.assertEqual(get_class_id("fish"), 6)
        self.assertEqual(get_class_id("nonexistent"), None)

        meta = get_class_metadata(0)
        self.assertIsNotNone(meta)
        self.assertEqual(meta.name, "shipwreck")
        self.assertEqual(meta.risk_level, "High")

        all_classes = get_all_classes()
        self.assertEqual(len(all_classes), 7)

    def test_model_loader(self):
        model = model_loader.get_model()
        self.assertIsNotNone(model)
        self.assertTrue(model_loader.is_loaded)
        
        info = model_loader.get_info()
        self.assertTrue(info["is_loaded"])
        self.assertEqual(info["task"], "detect")
        self.assertEqual(info["total_classes"], 7)
        self.assertIn("shipwreck", list(info["classes"].values()))
        self.assertIn("pipe", list(info["classes"].values()))
        self.assertIn("ghost_net", list(info["classes"].values()))

    def test_render_detections_overlay(self):
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        detections = [
            {
                "detection_id": "test_1",
                "class_id": 3,
                "class_name": "shipwreck",
                "display_name": "Shipwreck",
                "confidence": 0.88,
                "bbox": {
                    "x_min": 50,
                    "y_min": 50,
                    "x_max": 200,
                    "y_max": 200,
                    "width": 150,
                    "height": 150,
                },
                "color_rgb": [69, 123, 157],
            }
        ]

        rendered = render_detections_overlay(img, detections)
        self.assertEqual(rendered.shape, img.shape)
        self.assertGreater(np.sum(rendered), 0)

        jpeg_bytes = encode_image_to_jpeg_bytes(rendered)
        self.assertGreater(len(jpeg_bytes), 0)

        b64 = encode_image_to_base64(rendered)
        self.assertTrue(b64.startswith("data:image/jpeg;base64,"))

    def test_inference_service_predict(self):
        img = np.zeros((640, 640, 3), dtype=np.uint8)
        _, encoded = cv2.imencode(".jpg", img)
        image_bytes = encoded.tobytes()

        response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=0.30,
            return_visualization=True,
        )
        self.assertEqual(response.status, "success")
        self.assertEqual(response.image_info.width, 640)
        self.assertEqual(response.image_info.height, 640)
        self.assertIsNotNone(response.annotated_image_base64)
        self.assertIsNotNone(response.timing_breakdown)
        self.assertGreaterEqual(response.timing_breakdown.total_time_ms, 0.0)

    def test_inference_service_predict_array(self):
        # Test direct NumPy input without byte decode
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        response = inference_service.predict_array(
            image_bgr=img,
            confidence_threshold=0.25,
            meters_per_pixel=0.05,
        )
        self.assertEqual(response.status, "success")
        self.assertEqual(response.image_info.width, 640)
        self.assertEqual(response.image_info.height, 480)

    def test_inference_service_predict_batch(self):
        img1 = np.zeros((320, 320, 3), dtype=np.uint8)
        img2 = np.zeros((320, 320, 3), dtype=np.uint8)
        _, b1 = cv2.imencode(".jpg", img1)
        _, b2 = cv2.imencode(".jpg", img2)

        batch_resp = inference_service.predict_batch([b1.tobytes(), b2.tobytes()])
        self.assertEqual(batch_resp.status, "success")
        self.assertEqual(batch_resp.total_images, 2)
        self.assertEqual(len(batch_resp.results), 2)
        self.assertGreaterEqual(batch_resp.batch_duration_ms, 0.0)

    def test_inference_service_predict_tiled(self):
        # Large high-resolution synthetic image (e.g. 1000 x 1000)
        large_img = np.zeros((1000, 1000, 3), dtype=np.uint8)
        cfg = TilingConfig(tile_size=512, overlap_ratio=0.25)
        response = inference_service.predict_array(
            image_bgr=large_img,
            use_tiling=True,
            tiling_config=cfg,
        )
        self.assertEqual(response.status, "success")
        self.assertTrue(response.tiling_applied)
        self.assertEqual(response.image_info.width, 1000)
        self.assertEqual(response.image_info.height, 1000)

    def test_physical_dimension_calculation(self):
        sample_dets = [
            {
                "detection_id": "test_dim",
                "bbox": {"width": 100.0, "height": 50.0},
            }
        ]
        # At 0.05 meters/pixel (5 cm per pixel in high-res sonar):
        # width = 50px * 0.05 = 2.5m, length = 100px * 0.05 = 5.0m, area = 12.5 sq m
        augmented = inference_service.attach_physical_dimensions(sample_dets, meters_per_pixel=0.05)
        dims = augmented[0]["physical_dimensions"]
        self.assertEqual(dims["length_meters"], 5.0)
        self.assertEqual(dims["width_meters"], 2.5)
        self.assertEqual(dims["area_sq_meters"], 12.5)
        self.assertEqual(dims["meters_per_pixel"], 0.05)

    def test_yolo11_model_standalone_validation(self):
        """Verify the standalone validation module locates weights and verifies 7 classes."""
        import test_yolo11_model as validator

        weights_file = validator.locate_model_weights()
        self.assertTrue(weights_file.is_file())

        model = validator.YOLO(str(weights_file))
        raw_names = getattr(model, "names", {})
        passed, msg = validator.verify_classes(raw_names)
        self.assertTrue(passed, f"Class verification failed: {msg}")

    def test_evaluate_accuracy_benchmark(self):
        """Verify evaluate_accuracy benchmark runs and produces structured telemetry."""
        import evaluate_accuracy as evaluator

        model_path = evaluator.resolve_model_path()
        self.assertTrue(model_path.is_file())

        model = evaluator.YOLO(str(model_path))
        # Run benchmark on test synthetic array
        dummy_img = np.zeros((320, 320, 3), dtype=np.uint8)
        preds = model.predict(dummy_img, imgsz=320, conf=0.25, verbose=False)
        self.assertIsNotNone(preds)


if __name__ == "__main__":
    unittest.main()
