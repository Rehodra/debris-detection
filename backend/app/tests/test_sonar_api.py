"""
Unit and integration tests for MarineScan Raw Sonar API (/api/v1/sonar).
Tests format validation, parser selection, metadata inspection, raster generation,
error handling, and memory cleanup using synthetic XTF and JSF buffers.
"""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.tests.test_jsf_parser import build_synthetic_jsf_binary
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


class TestSonarAPI(unittest.TestCase):
    """
    Test suite for FastAPI Sonar API endpoints.
    """

    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def test_01_unsupported_extension(self):
        """
        Reject non-sonar extensions (e.g. .csv, .jpg, .txt) with HTTP 400.
        """
        fake_csv = io.BytesIO(b"timestamp,lat,lon\n2021-01-01,24.8,67.0")
        resp_inspect = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("survey.csv", fake_csv, "text/csv")},
        )
        self.assertEqual(resp_inspect.status_code, 400)
        self.assertIn("Unsupported file format", resp_inspect.json()["detail"])

        fake_jpg = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00")
        resp_raster = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("photo.jpg", fake_jpg, "image/jpeg")},
        )
        self.assertEqual(resp_raster.status_code, 400)
        self.assertIn("Unsupported file format", resp_raster.json()["detail"])

    def test_02_invalid_xtf_content(self):
        """
        Reject files with .xtf extension but corrupt or invalid binary content with HTTP 400.
        """
        corrupt_data = io.BytesIO(b"This is not a real XTF recording header!")
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("corrupt.xtf", corrupt_data, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("failed XTF format validation", resp.json()["detail"])

        corrupt_data.seek(0)
        resp_raster = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("corrupt.xtf", corrupt_data, "application/octet-stream")},
        )
        self.assertEqual(resp_raster.status_code, 400)
        self.assertIn("failed XTF format validation", resp_raster.json()["detail"])

    def test_03_invalid_jsf_content(self):
        """
        Reject files with .jsf extension but corrupt or invalid binary content with HTTP 400.
        """
        corrupt_data = io.BytesIO(b"EdgeTech JSF fake data without 0x1601 start marker!")
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("corrupt.jsf", corrupt_data, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("failed JSF format validation", resp.json()["detail"])

        corrupt_data.seek(0)
        resp_raster = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("corrupt.jsf", corrupt_data, "application/octet-stream")},
        )
        self.assertEqual(resp_raster.status_code, 400)
        self.assertIn("failed JSF format validation", resp_raster.json()["detail"])

    def test_04_parser_selection(self):
        """
        Correctly identify and select XtfSonarParser for .xtf and JsfSonarParser for .jsf.
        """
        xtf_buf = io.BytesIO(build_synthetic_xtf_binary(num_pings=3))
        resp_xtf = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("survey_data.xtf", xtf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_xtf.status_code, 200)
        self.assertEqual(resp_xtf.json()["format"], "XTF")

        jsf_buf = io.BytesIO(build_synthetic_jsf_binary(num_pings=3))
        resp_jsf = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("survey_data.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_jsf.status_code, 200)
        self.assertEqual(resp_jsf.json()["format"], "JSF")

    def test_05_inspect_endpoint(self):
        """
        Verify metadata inspection returns normalized JSON without acoustic arrays.
        """
        jsf_buf = io.BytesIO(
            build_synthetic_jsf_binary(
                num_pings=5,
                samples_per_chan=100,
                lat=24.8607,
                lon=67.0011,
                heading=185.0,
                altitude=10.5,
                depth=18.2,
            )
        )
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("edgetech_test.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["filename"], "edgetech_test.jsf")
        self.assertEqual(data["format"], "JSF")
        self.assertEqual(data["total_pings"], 5)
        self.assertEqual(data["channel_count"], 2)
        self.assertTrue(data["navigation_available"])
        self.assertIsNotNone(data["telemetry"])
        self.assertAlmostEqual(data["telemetry"]["latitude"], 24.8607, places=4)
        self.assertAlmostEqual(data["telemetry"]["longitude"], 67.0011, places=4)
        self.assertAlmostEqual(data["telemetry"]["heading_deg"], 185.0, places=1)
        self.assertAlmostEqual(data["telemetry"]["altitude_m"], 10.5, places=1)
        self.assertAlmostEqual(data["telemetry"]["depth_m"], 18.2, places=1)

        # Ensure no heavy acoustic sample arrays are leaked in inspect response
        self.assertNotIn("samples", data)
        self.assertNotIn("raster", data)

    def test_06_raster_endpoint(self):
        """
        Verify that raster generation returns valid image/png and companion metadata headers.
        """
        xtf_buf = io.BytesIO(build_synthetic_xtf_binary(num_pings=4, samples_per_chan=120))
        resp = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("sonar_scan.xtf", xtf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "image/png")

        # Decode image bytes to verify PNG integrity
        img_array = np.frombuffer(resp.content, dtype=np.uint8)
        decoded = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, (4, 240))  # 4 pings x 240 range bins (120 port + 120 stbd)

        # Check metadata headers
        self.assertEqual(resp.headers["X-Raster-Width"], "240")
        self.assertEqual(resp.headers["X-Raster-Height"], "4")
        self.assertEqual(resp.headers["X-Sonar-Format"], "XTF")
        self.assertIn("X-Sonar-Metadata", resp.headers)

        meta = json.loads(resp.headers["X-Sonar-Metadata"])
        self.assertEqual(meta["width"], 240)
        self.assertEqual(meta["height"], 4)
        self.assertEqual(meta["channel_layout"], "port_nadir_starboard")

    def test_07_max_pings_parameter(self):
        """
        Verify that max_pings bounds along-track raster height, and invalid values yield 422.
        """
        jsf_buf = io.BytesIO(build_synthetic_jsf_binary(num_pings=10, samples_per_chan=60))
        resp = self.client.post(
            "/api/v1/sonar/raster?max_pings=3",
            files={"file": ("survey_pings.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["X-Raster-Height"], "3")

        # Negative / zero max_pings should be rejected with HTTP 422
        jsf_buf.seek(0)
        resp_invalid = self.client.post(
            "/api/v1/sonar/raster?max_pings=0",
            files={"file": ("survey_pings.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_invalid.status_code, 422)

    def test_08_channel_selection(self):
        """
        Verify selective channel rendering (port-only, starboard-only, dual) and validation.
        """
        # Port only
        buf_p = io.BytesIO(build_synthetic_jsf_binary(num_pings=4, samples_per_chan=50))
        resp_p = self.client.post(
            "/api/v1/sonar/raster?channels=0",
            files={"file": ("port_test.jsf", buf_p, "application/octet-stream")},
        )
        self.assertEqual(resp_p.status_code, 200)
        self.assertEqual(resp_p.headers["X-Channel-Layout"], "port_only")
        self.assertEqual(resp_p.headers["X-Raster-Width"], "50")

        # Starboard only
        buf_s = io.BytesIO(build_synthetic_jsf_binary(num_pings=4, samples_per_chan=50))
        resp_s = self.client.post(
            "/api/v1/sonar/raster?channels=1",
            files={"file": ("stbd_test.jsf", buf_s, "application/octet-stream")},
        )
        self.assertEqual(resp_s.status_code, 200)
        self.assertEqual(resp_s.headers["X-Channel-Layout"], "starboard_only")
        self.assertEqual(resp_s.headers["X-Raster-Width"], "50")

        # Invalid non-integer channel
        buf_bad = io.BytesIO(build_synthetic_jsf_binary(num_pings=2))
        resp_bad = self.client.post(
            "/api/v1/sonar/raster?channels=invalid_channel",
            files={"file": ("bad_ch.jsf", buf_bad, "application/octet-stream")},
        )
        self.assertEqual(resp_bad.status_code, 422)

        # Invalid negative channel
        buf_neg = io.BytesIO(build_synthetic_jsf_binary(num_pings=2))
        resp_neg = self.client.post(
            "/api/v1/sonar/raster?channels=-1",
            files={"file": ("neg_ch.jsf", buf_neg, "application/octet-stream")},
        )
        self.assertEqual(resp_neg.status_code, 422)

    def test_09_malformed_upload(self):
        """
        Handle severely truncated binary files gracefully with HTTP 400.
        """
        trunc_buf = io.BytesIO(build_synthetic_jsf_binary(num_pings=3)[:15])
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("truncated.jsf", trunc_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)

        trunc_buf.seek(0)
        resp_raster = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("truncated.jsf", trunc_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_raster.status_code, 400)

    def test_10_missing_and_empty_upload(self):
        """
        Missing file field returns HTTP 422, empty file returns HTTP 400.
        """
        # Missing upload field
        resp_missing = self.client.post("/api/v1/sonar/inspect")
        self.assertEqual(resp_missing.status_code, 422)

        # Empty file (0 bytes)
        empty_buf = io.BytesIO(b"")
        resp_empty = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("empty.xtf", empty_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_empty.status_code, 400)
        self.assertIn("empty", resp_empty.json()["detail"].lower())

    def test_11_metadata_serialization(self):
        """
        Ensure metadata fields safely serialize to JSON without NaN, Inf, or formatting issues.
        """
        # Test file with unlogged / None navigation fields
        jsf_buf = io.BytesIO(
            build_synthetic_jsf_binary(
                num_pings=3,
                lat=None,
                lon=None,
                heading=None,
                altitude=None,
                depth=None,
            )
        )
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("no_nav.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["navigation_available"])

        # Check raster companion header format
        jsf_buf.seek(0)
        resp_r = self.client.post(
            "/api/v1/sonar/raster",
            files={"file": ("no_nav.jsf", jsf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp_r.status_code, 200)
        meta = json.loads(resp_r.headers["X-Sonar-Metadata"])
        self.assertIsInstance(meta, dict)
        self.assertIn("channel_layout", meta)

    def test_12_error_responses_no_stack_traces(self):
        """
        Confirm error responses return clean JSON details without exposing internal stack traces.
        """
        junk_buf = io.BytesIO(b"random junk bytes that are not sonar data")
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("bad_header.xtf", junk_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json().get("detail", "")
        self.assertNotIn("Traceback (most recent call last)", detail)
        self.assertNotIn("File \"", detail)

    def test_13_temporary_file_cleanup(self):
        """
        Verify that temporary files created during request streaming are cleanly removed.
        """
        temp_dir = Path(tempfile.gettempdir())
        before_xtf_files = set(temp_dir.glob("*.xtf"))

        xtf_buf = io.BytesIO(build_synthetic_xtf_binary(num_pings=2))
        resp = self.client.post(
            "/api/v1/sonar/inspect",
            files={"file": ("cleanup_test.xtf", xtf_buf, "application/octet-stream")},
        )
        self.assertEqual(resp.status_code, 200)

        after_xtf_files = set(temp_dir.glob("*.xtf"))
        leaked_files = after_xtf_files - before_xtf_files
        self.assertEqual(len(leaked_files), 0, f"Temporary files were not cleaned up: {leaked_files}")

    def test_14_openapi_docs_registration(self):
        """
        Verify that the new sonar endpoints are exposed in /api/v1/openapi.json and /docs.
        """
        resp = self.client.get("/api/v1/openapi.json")
        self.assertEqual(resp.status_code, 200)
        schema = resp.json()
        paths = schema.get("paths", {})

        self.assertIn("/api/v1/sonar/inspect", paths)
        self.assertIn("/api/v1/sonar/raster", paths)
        self.assertIn("post", paths["/api/v1/sonar/inspect"])
        self.assertIn("post", paths["/api/v1/sonar/raster"])

        # Also verify /docs loads successfully
        docs_resp = self.client.get("/docs")
        self.assertEqual(docs_resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
