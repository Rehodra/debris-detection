import unittest
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get(f"{settings.API_V1_STR}/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "marinescan"
            }
        )

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("health_check", data)
        self.assertEqual(data["health_check"], "/api/v1/health")


if __name__ == "__main__":
    unittest.main()
