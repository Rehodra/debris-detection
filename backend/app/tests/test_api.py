import io
import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.ml.model_loader import model_loader




class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg(self, width: int = 640, height: int = 640) -> io.BytesIO:
        """Helper to create an in-memory sample JPEG image."""
        img = np.zeros((height, width, 3), dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (300, 300), (180, 180, 180), -1)
        cv2.circle(img, (450, 450), 80, (220, 220, 220), -1)
        success, encoded = cv2.imencode(".jpg", img)
        return io.BytesIO(encoded.tobytes())

    def test_health_check(self):
        response = self.client.get(f"{settings.API_V1_STR}/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "marinescan")
        self.assertIn("model_loaded", data)
        self.assertIn("model_device", data)
        self.assertTrue(data["model_loaded"])

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("health_check", data)
        self.assertEqual(data["health_check"], "/api/v1/health")
        self.assertIn("models_endpoint", data)
        self.assertIn("detections_endpoint", data)

    def test_health_check(self):
        response = self.client.get(f"{settings.API_V1_STR}/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "marinescan")
        self.assertIn("model_loaded", data)
        self.assertIn("model_device", data)
        self.assertTrue(data["model_loaded"])

    def test_get_current_model(self):
        response = self.client.get(f"{settings.API_V1_STR}/models/current")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_loaded"])
        self.assertEqual(data["total_classes"], 4)
        self.assertEqual(data["task"], "detect")
        self.assertIn("classes", data)
        self.assertIn("aircraft", list(data["classes"].values()))
        self.assertIn("shipwreck", list(data["classes"].values()))

    def test_get_model_classes(self):
        response = self.client.get(f"{settings.API_V1_STR}/models/classes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 4)
        class_names = [c["name"] for c in data]
        self.assertIn("aircraft", class_names)
        self.assertIn("fish", class_names)
        self.assertIn("other", class_names)
        self.assertIn("shipwreck", class_names)

        for item in data:
            self.assertIn("display_name", item)
            self.assertIn("risk_level", item)
            self.assertIn("color_hex", item)
            self.assertIn("color_rgb", item)

    def test_reload_model(self):
        response = self.client.post(f"{settings.API_V1_STR}/models/reload")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["is_loaded"])
        self.assertEqual(data["total_classes"], 4)

    def test_predict_detections_endpoint(self):
        img_buf = self._create_sample_jpeg()
        files = {"file": ("test_sonar.jpg", img_buf.getvalue(), "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict?confidence_threshold=0.25&return_visualization=true",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("inference_time_ms", data)
        self.assertIn("detections", data)
        self.assertIn("summary", data)
        self.assertIn("image_info", data)
        self.assertEqual(data["image_info"]["width"], 640)
        self.assertEqual(data["image_info"]["height"], 640)
        self.assertIsNotNone(data["annotated_image_base64"])
        self.assertTrue(data["annotated_image_base64"].startswith("data:image/jpeg;base64,"))

    def test_predict_with_class_filter(self):
        img_buf = self._create_sample_jpeg()
        files = {"file": ("test_sonar.jpg", img_buf.getvalue(), "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict?classes=shipwreck&classes=aircraft",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        for det in data["detections"]:
            self.assertIn(det["class_name"], ["shipwreck", "aircraft"])

    def test_visualize_endpoint(self):
        img_buf = self._create_sample_jpeg()
        files = {"file": ("test_sonar.jpg", img_buf.getvalue(), "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/visualize?confidence_threshold=0.25",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertIn("X-Detections-Count", response.headers)
        self.assertGreater(len(response.content), 0)

    def test_predict_with_meters_per_pixel(self):
        img_buf = self._create_sample_jpeg()
        files = {"file": ("test_sonar.jpg", img_buf.getvalue(), "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict?meters_per_pixel=0.08",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")

    def test_predict_batch_endpoint(self):
        buf1 = self._create_sample_jpeg()
        buf2 = self._create_sample_jpeg()
        files = [
            ("files", ("scan_1.jpg", buf1.getvalue(), "image/jpeg")),
            ("files", ("scan_2.jpg", buf2.getvalue(), "image/jpeg")),
        ]
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict-batch",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_images"], 2)
        self.assertEqual(len(data["results"]), 2)

    def test_predict_empty_file_fails(self):
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict",
            files=files,
        )
        self.assertEqual(response.status_code, 400)

    def test_predict_invalid_image_fails(self):
        files = {"file": ("corrupt.jpg", b"not-a-valid-image-content", "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/detections/predict",
            files=files,
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
