"""
Unit and integration tests for Phase 6B: Analysis Artifact & Stable Sonar Raster Retrieval.

Validates:
1. Test 1 — XTF artifact creation: XTF input -> analysis -> analysis ID -> waterfall artifact.
2. Test 2 — JSF artifact creation: JSF input -> analysis -> analysis ID -> waterfall artifact.
3. Test 3 — Stable raster retrieval: GET /api/v1/analyses/{analysis_id}/sonar/raster returns 200, valid PNG, correct dimensions.
4. Test 4 — Metadata consistency: metadata.waterfall_width == raster.width, metadata.waterfall_height == raster.height.
5. Test 5 — Repeated retrieval: Multiple fetches return identical binary artifact bytes.
6. Test 6 — Invalid analysis ID: GET /api/v1/analyses/{invalid_id}/sonar/raster returns 404.
7. Test 7 — Non-sonar analysis: Normal PNG/JPG analysis returns 404 when querying sonar raster endpoint.
8. Test 8 — Cross-analysis isolation: Analyses A and B return their own distinct raster artifacts.
9. Test 9 — max_pings preservation: Analysis with specific max_pings stores artifact matching requested pings.
10. Test 10 — Channel selection preservation: Analysis with explicit channels stores artifact matching that channel layout.
11. Test 11 — Missing artifact handling: When stored artifact file is removed, returns clean error without silent regeneration.
12. Test 12 — Artifact cleanup: Tests artifact deletion and lifecycle pruning routines.
"""

import hashlib
import io
import json
import unittest
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import SonarAnalysisResponse
from app.services.master_pipeline_service import master_pipeline_service
from app.services.sonar_artifact_service import SonarArtifactService, sonar_artifact_service
from app.tests.test_jsf_parser import build_synthetic_jsf_binary
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


class TestSonarArtifactRetrieval(unittest.TestCase):
    """
    Test suite for Phase 6B: Stable Sonar Waterfall Raster Artifact Lifecycle & Retrieval.
    """

    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self, width: int = 100, height: int = 100) -> bytes:
        img = np.full((height, width, 3), 80, dtype=np.uint8)
        cv2.circle(img, (50, 50), 20, (200, 200, 200), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def _create_sample_png_bytes(self, width: int = 100, height: int = 100) -> bytes:
        img = np.full((height, width, 3), 60, dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (60, 60), (220, 220, 220), -1)
        _, buf = cv2.imencode(".png", img)
        return buf.tobytes()

    # -------------------------------------------------------------------------
    # Test 1: XTF Artifact Creation
    # -------------------------------------------------------------------------
    def test_01_xtf_artifact_creation(self):
        """
        Verify that XTF analysis creates an analysis ID, associates a waterfall artifact,
        and provides a valid raster reference in the response.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=12,
            samples_per_chan=64,
            lat=24.8607,
            lon=67.0011,
            heading=180.0,
            altitude=15.0,
            depth=20.0,
        )

        response = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("transect_01.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        analysis_id = data.get("mission_id")
        self.assertIsNotNone(analysis_id)
        self.assertTrue(analysis_id.startswith("msn_"))

        # Verify sonar metadata and artifact association
        sonar_meta = data.get("sonar")
        self.assertIsNotNone(sonar_meta)
        expected_ref = f"/api/v1/analyses/{analysis_id}/sonar/raster"
        self.assertEqual(sonar_meta.get("raster_reference"), expected_ref)
        self.assertEqual(sonar_meta.get("artifact_id"), f"art_{analysis_id}")
        self.assertEqual(sonar_meta.get("waterfall_height"), 12)
        self.assertEqual(sonar_meta.get("waterfall_width"), 128)  # 64 port + 64 stbd

        # Verify physical artifact exists in storage
        self.assertTrue(sonar_artifact_service.has_artifact(analysis_id))
        artifact_bytes = sonar_artifact_service.get_artifact_bytes(analysis_id)
        self.assertIsNotNone(artifact_bytes)
        self.assertGreater(len(artifact_bytes), 0)

    # -------------------------------------------------------------------------
    # Test 2: JSF Artifact Creation
    # -------------------------------------------------------------------------
    def test_02_jsf_artifact_creation(self):
        """
        Verify that JSF analysis creates an analysis ID, associates a waterfall artifact,
        and provides a valid raster reference in the response.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=10,
            samples_per_chan=80,
            lat=24.8607,
            lon=67.0011,
            heading=90.0,
            altitude=12.0,
            depth=18.0,
        )

        response = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_run.jsf", jsf_bytes, "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        analysis_id = data.get("mission_id")
        self.assertIsNotNone(analysis_id)

        sonar_meta = data.get("sonar")
        self.assertIsNotNone(sonar_meta)
        expected_ref = f"/api/v1/analyses/{analysis_id}/sonar/raster"
        self.assertEqual(sonar_meta.get("raster_reference"), expected_ref)
        self.assertEqual(sonar_meta.get("artifact_id"), f"art_{analysis_id}")
        self.assertEqual(sonar_meta.get("waterfall_height"), 10)
        self.assertEqual(sonar_meta.get("waterfall_width"), 160)  # 80 port + 80 stbd

        # Verify physical artifact exists in storage
        self.assertTrue(sonar_artifact_service.has_artifact(analysis_id))

    # -------------------------------------------------------------------------
    # Test 3: Stable Raster Retrieval
    # -------------------------------------------------------------------------
    def test_03_stable_raster_retrieval(self):
        """
        Verify that GET /api/v1/analyses/{analysis_id}/sonar/raster returns HTTP 200,
        content-type image/png, non-empty content, valid decodable PNG, and expected dimensions.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=15, samples_per_chan=50)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("retrieve_test.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(resp_post.status_code, 200)
        analysis_id = resp_post.json()["mission_id"]

        # Fetch artifact
        resp_get = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 200)
        self.assertEqual(resp_get.headers.get("content-type"), "image/png")
        self.assertGreater(len(resp_get.content), 0)

        # Decode PNG and verify dimensions
        np_arr = np.frombuffer(resp_get.content, dtype=np.uint8)
        decoded = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape[0], 15)   # height = pings
        self.assertEqual(decoded.shape[1], 100)  # width = 50 * 2

    # -------------------------------------------------------------------------
    # Test 4: Metadata Consistency
    # -------------------------------------------------------------------------
    def test_04_metadata_consistency(self):
        """
        Compare analysis metadata against the retrieved raster dimensions and headers.
        Verify: metadata.waterfall_width == raster.width, metadata.waterfall_height == raster.height.
        """
        jsf_bytes = build_synthetic_jsf_binary(num_pings=14, samples_per_chan=60)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("meta_check.jsf", jsf_bytes, "application/octet-stream")},
        )
        self.assertEqual(resp_post.status_code, 200)
        data = resp_post.json()
        analysis_id = data["mission_id"]
        sonar_meta = data["sonar"]

        resp_get = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 200)

        # Check headers
        self.assertEqual(resp_get.headers.get("x-analysis-id"), analysis_id)
        self.assertEqual(resp_get.headers.get("x-raster-width"), str(sonar_meta["waterfall_width"]))
        self.assertEqual(resp_get.headers.get("x-raster-height"), str(sonar_meta["waterfall_height"]))
        self.assertEqual(resp_get.headers.get("x-channel-layout"), str(sonar_meta["channel_layout"]))
        self.assertEqual(resp_get.headers.get("x-sonar-format"), "JSF")

        # Check decoded binary image
        np_arr = np.frombuffer(resp_get.content, dtype=np.uint8)
        decoded = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
        self.assertEqual(decoded.shape[1], sonar_meta["waterfall_width"])
        self.assertEqual(decoded.shape[0], sonar_meta["waterfall_height"])

        # Check JSON telemetry in header
        raw_json_meta = resp_get.headers.get("x-sonar-metadata")
        self.assertIsNotNone(raw_json_meta)
        header_meta = json.loads(raw_json_meta)
        self.assertEqual(header_meta["width"], sonar_meta["waterfall_width"])
        self.assertEqual(header_meta["height"], sonar_meta["waterfall_height"])

    # -------------------------------------------------------------------------
    # Test 5: Repeated Retrieval
    # -------------------------------------------------------------------------
    def test_05_repeated_retrieval(self):
        """
        Retrieve the same raster multiple times and verify exact binary equality.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=40)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("repeat_check.xtf", xtf_bytes, "application/octet-stream")},
        )
        analysis_id = resp_post.json()["mission_id"]

        resp_1 = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        resp_2 = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        resp_3 = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")

        self.assertEqual(resp_1.status_code, 200)
        self.assertEqual(resp_2.status_code, 200)
        self.assertEqual(resp_3.status_code, 200)

        hash_1 = hashlib.sha256(resp_1.content).hexdigest()
        hash_2 = hashlib.sha256(resp_2.content).hexdigest()
        hash_3 = hashlib.sha256(resp_3.content).hexdigest()

        self.assertEqual(hash_1, hash_2)
        self.assertEqual(hash_2, hash_3)

    # -------------------------------------------------------------------------
    # Test 6: Invalid Analysis ID
    # -------------------------------------------------------------------------
    def test_06_invalid_analysis_id(self):
        """
        Request GET /api/v1/analyses/{invalid_id}/sonar/raster with unknown ID;
        must return HTTP 404.
        """
        invalid_id = "msn_nonexistent_000000"
        resp = self.client.get(f"/api/v1/analyses/{invalid_id}/sonar/raster")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 7: Non-Sonar Analysis
    # -------------------------------------------------------------------------
    def test_07_non_sonar_analysis(self):
        """
        Create a standard JPEG or PNG analysis, then request its sonar raster endpoint.
        Must return HTTP 404 indicating it is not a raw sonar analysis.
        """
        jpeg_bytes = self._create_sample_jpeg_bytes()
        resp_post = self.client.post(
            "/api/v1/analyses/analyze",
            files={"file": ("camera_survey.jpg", jpeg_bytes, "image/jpeg")},
        )
        self.assertEqual(resp_post.status_code, 200)
        mission_id = resp_post.json()["mission_id"]

        resp_get = self.client.get(f"/api/v1/analyses/{mission_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 404)
        self.assertIn("not generated from a raw sonar", resp_get.json()["detail"])

    # -------------------------------------------------------------------------
    # Test 8: Cross-Analysis Isolation
    # -------------------------------------------------------------------------
    def test_08_cross_analysis_isolation(self):
        """
        Create two distinct sonar analyses (A and B) with different dimensions.
        Verify analysis A cannot return analysis B's raster and vice versa.
        """
        xtf_a = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=40)
        xtf_b = build_synthetic_xtf_binary(num_pings=16, samples_per_chan=70)

        resp_a = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_A.xtf", xtf_a, "application/octet-stream")},
        )
        resp_b = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_B.xtf", xtf_b, "application/octet-stream")},
        )

        id_a = resp_a.json()["mission_id"]
        id_b = resp_b.json()["mission_id"]
        self.assertNotEqual(id_a, id_b)

        get_a = self.client.get(f"/api/v1/analyses/{id_a}/sonar/raster")
        get_b = self.client.get(f"/api/v1/analyses/{id_b}/sonar/raster")

        self.assertEqual(get_a.status_code, 200)
        self.assertEqual(get_b.status_code, 200)

        dec_a = cv2.imdecode(np.frombuffer(get_a.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        dec_b = cv2.imdecode(np.frombuffer(get_b.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

        # Confirm A is 8x80, B is 16x140
        self.assertEqual(dec_a.shape, (8, 80))
        self.assertEqual(dec_b.shape, (16, 140))
        self.assertNotEqual(hashlib.sha256(get_a.content).hexdigest(), hashlib.sha256(get_b.content).hexdigest())

    # -------------------------------------------------------------------------
    # Test 9: max_pings Preservation
    # -------------------------------------------------------------------------
    def test_09_max_pings_preservation(self):
        """
        Create an analysis with explicit max_pings=6 on a 20-ping file.
        Verify the stored artifact dimensions correspond to requested max_pings.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=20, samples_per_chan=50)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar?max_pings=6",
            files={"file": ("bounded_pings.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(resp_post.status_code, 200)
        data = resp_post.json()
        analysis_id = data["mission_id"]
        self.assertEqual(data["sonar"]["waterfall_height"], 6)

        resp_get = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 200)

        decoded = cv2.imdecode(np.frombuffer(resp_get.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(decoded.shape[0], 6)
        self.assertEqual(decoded.shape[1], 100)

    # -------------------------------------------------------------------------
    # Test 10: Channel Selection Preservation
    # -------------------------------------------------------------------------
    def test_10_channel_selection_preservation(self):
        """
        Create an analysis with explicit single-channel selection channels=0 (port only).
        Verify the stored artifact matches the single-channel width (50px, not dual 100px).
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=10, samples_per_chan=50)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar?channels=0",
            files={"file": ("port_only.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(resp_post.status_code, 200)
        data = resp_post.json()
        analysis_id = data["mission_id"]
        self.assertEqual(data["sonar"]["waterfall_width"], 50)
        self.assertEqual(data["sonar"]["selected_channels"], [0])

        resp_get = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 200)

        decoded = cv2.imdecode(np.frombuffer(resp_get.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(decoded.shape[1], 50)
        self.assertEqual(decoded.shape[0], 10)

    # -------------------------------------------------------------------------
    # Test 11: Missing Artifact Handling
    # -------------------------------------------------------------------------
    def test_11_missing_artifact_handling(self):
        """
        Simulate a missing physical artifact file (e.g. storage loss) while metadata exists in DB.
        Verify a clear 404 is returned rather than silently regenerating unrelated data.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=5, samples_per_chan=30)
        resp_post = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("missing_art.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(resp_post.status_code, 200)
        analysis_id = resp_post.json()["mission_id"]

        # Physically unlink the artifact file
        path = sonar_artifact_service.get_artifact_path(analysis_id)
        self.assertIsNotNone(path)
        path.unlink()
        self.assertFalse(sonar_artifact_service.has_artifact(analysis_id))

        # Attempt retrieval
        resp_get = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(resp_get.status_code, 404)
        self.assertIn("physical artifact is missing from storage", resp_get.json()["detail"])

    # -------------------------------------------------------------------------
    # Test 12: Artifact Lifecycle & Cleanup
    # -------------------------------------------------------------------------
    def test_12_artifact_cleanup(self):
        """
        Verify artifact deletion and lifecycle pruning routines.
        """
        temp_id = f"test_cleanup_{hashlib.md5(b'cleanup').hexdigest()[:8]}"
        dummy_raster = np.full((10, 20), 128, dtype=np.uint8)

        # 1. Save artifact directly via service
        meta = sonar_artifact_service.save_waterfall_artifact(
            analysis_id=temp_id,
            raster=dummy_raster,
            metadata={"test_key": "test_val"},
        )
        self.assertTrue(sonar_artifact_service.has_artifact(temp_id))
        self.assertIsNotNone(sonar_artifact_service.get_artifact_metadata(temp_id))

        # 2. Test direct deletion
        deleted = sonar_artifact_service.delete_artifact(temp_id)
        self.assertTrue(deleted)
        self.assertFalse(sonar_artifact_service.has_artifact(temp_id))
        self.assertIsNone(sonar_artifact_service.get_artifact_metadata(temp_id))

        # 3. Test pruning by age
        temp_id2 = f"test_cleanup_age_{hashlib.md5(b'age').hexdigest()[:8]}"
        sonar_artifact_service.save_waterfall_artifact(
            analysis_id=temp_id2,
            raster=dummy_raster,
        )
        self.assertTrue(sonar_artifact_service.has_artifact(temp_id2))
        # Setting max_age_seconds to -1 forces all files older than current timestamp to be pruned
        pruned_count = sonar_artifact_service.cleanup_old_artifacts(max_age_seconds=-1.0)
        self.assertGreaterEqual(pruned_count, 1)
        self.assertFalse(sonar_artifact_service.has_artifact(temp_id2))


if __name__ == "__main__":
    unittest.main()
