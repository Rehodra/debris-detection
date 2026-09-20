"""
Unit and integration tests for Phase 7: Hydrographic / Navigation Data Packaging & Export.

Tests:
1. Test 1 — JSON export: HTTP 200, valid JSON, analysis ID, sonar metadata, navigation, detections.
2. Test 2 — CSV export: HTTP 200, text/csv, header row, detection rows, bounding box fields.
3. Test 3 — GeoJSON export: HTTP 200, application/geo+json, FeatureCollection, valid features, [lon, lat] order.
4. Test 4 — WGS84 coordinate correctness: Known coordinates preserved in strictly [longitude, latitude] GeoJSON order.
5. Test 5 — Missing navigation: Unlogged navigation coordinates strictly remain null, never 0,0 or fake coordinates.
6. Test 6 — Missing geolocation: Missing target coordinates do not produce fake coordinates; returns empty FeatureCollection.
7. Test 7 — Artifact reference: JSON export references raster artifact, contains no base64 raster data, no internal paths.
8. Test 8 — Metadata consistency: Exported sonar metadata matches original analysis result.
9. Test 9 — Invalid analysis ID: Querying non-existent analysis returns 404 for json, csv, and geojson endpoints.
10. Test 10 — Standard image analysis: Standard PNG/JPG analysis exports cleanly without requiring sonar-only fields.
11. Test 11 — Multiple detections: All detections faithfully packaged across JSON, CSV, and GeoJSON.
12. Test 12 — No cross-analysis leakage: Exports from Analysis A never leak into Analysis B.
"""

import csv
import io
import json
import unittest
from datetime import datetime, timezone

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.db.models import AnalysisRecord
from app.db.session import SessionLocal
from app.main import app
from app.services.hydrographic_export_service import (
    EXPORT_SCHEMA_VERSION,
    HydrographicExportService,
    hydrographic_export_service,
)
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


class TestHydrographicExport(unittest.TestCase):
    """Complete test suite for Phase 7 Hydrographic & Navigation Data Export."""

    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self, width: int = 120, height: int = 120) -> bytes:
        img = np.full((height, width, 3), 80, dtype=np.uint8)
        cv2.circle(img, (60, 60), 25, (200, 200, 200), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    # -------------------------------------------------------------------------
    # Test 1: JSON Export
    # -------------------------------------------------------------------------
    def test_01_json_export(self):
        """Verify full structured JSON export from completed sonar analysis."""
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=10,
            samples_per_chan=64,
            lat=24.8607,
            lon=67.0011,
            heading=90.0,
            altitude=12.0,
            depth=18.0,
        )
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_run_01.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200, f"Analysis failed: {post_resp.text}")
        analysis_id = post_resp.json()["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/json")
        self.assertEqual(export_resp.status_code, 200)
        self.assertIn("application/json", export_resp.headers["content-type"])
        self.assertIn(f'filename="marinescan_{analysis_id}.json"', export_resp.headers["content-disposition"])

        data = export_resp.json()
        self.assertEqual(data["schema_version"], EXPORT_SCHEMA_VERSION)
        self.assertEqual(data["analysis"]["analysis_id"], analysis_id)
        self.assertEqual(data["analysis"]["sonar_format"], "XTF")
        self.assertEqual(data["analysis"]["original_filename"], "survey_run_01.xtf")
        self.assertIn("navigation", data)
        self.assertAlmostEqual(data["navigation"]["latitude"], 24.8607, places=4)
        self.assertAlmostEqual(data["navigation"]["longitude"], 67.0011, places=4)
        self.assertEqual(data["navigation"]["heading"], 90.0)
        self.assertIn("detections", data)
        self.assertIsInstance(data["detections"], list)
        self.assertIn("summary", data)

    # -------------------------------------------------------------------------
    # Test 2: CSV Export
    # -------------------------------------------------------------------------
    def test_02_csv_export(self):
        """Verify CSV detection export with correct content type and headers."""
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_run_02.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/csv")
        self.assertEqual(export_resp.status_code, 200)
        self.assertIn("text/csv", export_resp.headers["content-type"])
        self.assertIn(f'filename="marinescan_{analysis_id}.csv"', export_resp.headers["content-disposition"])

        csv_text = export_resp.text
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 1, "CSV must contain at least the header row")

        headers = rows[0]
        expected_cols = [
            "analysis_id",
            "detection_id",
            "class",
            "confidence",
            "x_min",
            "y_min",
            "x_max",
            "y_max",
            "normalized_x_min",
            "normalized_y_min",
            "normalized_x_max",
            "normalized_y_max",
            "latitude",
            "longitude",
            "risk_score",
            "risk_tier",
        ]
        for col in expected_cols:
            self.assertIn(col, headers, f"Header column '{col}' missing from CSV export")

    # -------------------------------------------------------------------------
    # Test 3: GeoJSON Export
    # -------------------------------------------------------------------------
    def test_03_geojson_export(self):
        """Verify RFC 7946 GeoJSON FeatureCollection export."""
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=10,
            samples_per_chan=64,
            lat=24.8607,
            lon=67.0011,
            heading=45.0,
        )
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_run_03.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/geojson")
        self.assertEqual(export_resp.status_code, 200)
        self.assertIn("application/geo+json", export_resp.headers["content-type"])
        self.assertIn(f'filename="marinescan_{analysis_id}.geojson"', export_resp.headers["content-disposition"])

        geojson = export_resp.json()
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["analysis_id"], analysis_id)
        self.assertEqual(geojson["schema_version"], EXPORT_SCHEMA_VERSION)
        self.assertIsInstance(geojson["features"], list)

        for feature in geojson["features"]:
            self.assertEqual(feature["type"], "Feature")
            self.assertEqual(feature["geometry"]["type"], "Point")
            coords = feature["geometry"]["coordinates"]
            self.assertEqual(len(coords), 2)
            # Longitude in [-180, 180], Latitude in [-90, 90]
            self.assertTrue(-180.0 <= coords[0] <= 180.0)
            self.assertTrue(-90.0 <= coords[1] <= 90.0)
            self.assertIn("analysis_id", feature["properties"])
            self.assertIn("class", feature["properties"])
            self.assertIn("confidence", feature["properties"])

    # -------------------------------------------------------------------------
    # Test 4: WGS84 Coordinate Correctness (Strict [longitude, latitude] Order)
    # -------------------------------------------------------------------------
    def test_04_wgs84_coordinate_correctness(self):
        """
        Verify that coordinates strictly adhere to RFC 7946:
        coordinates = [longitude, latitude] (NOT [latitude, longitude]).
        """
        known_lat = 25.1234567
        known_lon = 68.7654321

        synthetic_result = {
            "mission_id": "test_coords_msn",
            "targets": [
                {
                    "detection_id": "det_target_01",
                    "class_name": "shipwreck",
                    "display_name": "Shipwreck",
                    "category": "Maritime Hazard",
                    "calibrated_confidence": 0.92,
                    "ai_confidence": 0.88,
                    "trust_tier": "HIGH",
                    "coordinates": {
                        "latitude": known_lat,
                        "longitude": known_lon,
                        "dms_string": "25° 07' 24.4\" N, 068° 45' 55.6\" E",
                        "utm_zone": "42N",
                        "utm_easting_m": 476320.0,
                        "utm_northing_m": 2778910.0,
                    },
                    "bbox": {"x_min": 10.0, "y_min": 20.0, "x_max": 50.0, "y_max": 60.0},
                    "dimensions": {"length_m": 15.0, "width_m": 5.0, "height_m": 2.5},
                    "risk_score": 85.0,
                    "risk_tier": "HIGH",
                }
            ],
        }

        geojson = hydrographic_export_service.export_geojson(synthetic_result, analysis_id="test_coords_msn")
        self.assertEqual(len(geojson["features"]), 1)
        coords = geojson["features"][0]["geometry"]["coordinates"]

        # Element 0 MUST be longitude, Element 1 MUST be latitude
        self.assertEqual(coords[0], known_lon, "GeoJSON coordinate 0 must be longitude")
        self.assertEqual(coords[1], known_lat, "GeoJSON coordinate 1 must be latitude")

    # -------------------------------------------------------------------------
    # Test 5: Missing Navigation (Preserves null, Never 0,0)
    # -------------------------------------------------------------------------
    def test_05_missing_navigation_preserves_null(self):
        """Verify unlogged navigation coordinates strictly remain null without fake sentinels."""
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=8,
            samples_per_chan=64,
            lat=None,
            lon=None,
            heading=None,
            altitude=None,
            depth=None,
        )
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_unlogged_nav.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/json")
        self.assertEqual(export_resp.status_code, 200)
        nav = export_resp.json()["navigation"]

        self.assertIsNone(nav["latitude"], "Missing latitude must remain None (null)")
        self.assertIsNone(nav["longitude"], "Missing longitude must remain None (null)")
        self.assertIsNone(nav["heading"], "Missing heading must remain None (null)")
        self.assertIsNone(nav["altitude"], "Missing altitude must remain None (null)")
        self.assertIsNone(nav["depth"], "Missing depth must remain None (null)")

    # -------------------------------------------------------------------------
    # Test 6: Missing Geolocation
    # -------------------------------------------------------------------------
    def test_06_missing_geolocation_no_fake_coordinates(self):
        """
        Verify that targets missing valid coordinates are never assigned (0,0)
        or fake coordinates, returning an empty FeatureCollection when none are valid.
        """
        synthetic_result = {
            "mission_id": "test_missing_geo",
            "targets": [
                {
                    "detection_id": "det_no_geo_01",
                    "class_name": "other",
                    "display_name": "Unknown Anomaly",
                    "calibrated_confidence": 0.45,
                    "coordinates": {
                        "latitude": None,
                        "longitude": None,
                    },
                }
            ],
        }

        geojson = hydrographic_export_service.export_geojson(synthetic_result, analysis_id="test_missing_geo")
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["features"], [], "Targets with null coordinates must not produce fake features")

    # -------------------------------------------------------------------------
    # Test 7: Artifact Reference (No base64 data, No server paths)
    # -------------------------------------------------------------------------
    def test_07_artifact_reference_integrity(self):
        """
        Verify JSON export contains artifact_id and raster_reference,
        does not contain base64 image data, and does not leak local filesystem paths.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=10, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_art_test.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/json")
        self.assertEqual(export_resp.status_code, 200)
        data = export_resp.json()

        artifact = data.get("artifact")
        self.assertIsNotNone(artifact, "Sonar analysis export must include artifact reference")
        self.assertIn("artifact_id", artifact)
        self.assertIn("raster_reference", artifact)
        self.assertTrue(artifact["raster_reference"].startswith(f"/api/v1/analyses/{analysis_id}/sonar/raster"))

        # Verify no base64 payloads
        raw_json_str = export_resp.text
        self.assertNotIn("data:image/png;base64,", raw_json_str)
        self.assertNotIn("data:image/jpeg;base64,", raw_json_str)

        # Verify no internal server filesystem paths in artifact block
        self.assertNotIn("raster_path", artifact)
        self.assertNotIn("/Users/", raw_json_str)
        self.assertNotIn("/tmp/", raw_json_str)

    # -------------------------------------------------------------------------
    # Test 8: Metadata Consistency
    # -------------------------------------------------------------------------
    def test_08_metadata_consistency(self):
        """Compare exported sonar metadata against original analysis result."""
        xtf_bytes = build_synthetic_xtf_binary(num_pings=12, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey_meta_consist.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        orig_data = post_resp.json()
        analysis_id = orig_data["mission_id"]

        export_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/export/json")
        self.assertEqual(export_resp.status_code, 200)
        export_data = export_resp.json()

        orig_sonar = orig_data.get("sonar_metadata") or {}
        export_art = export_data.get("artifact") or {}

        self.assertEqual(export_art["raster_width"], orig_sonar.get("waterfall_width"))
        self.assertEqual(export_art["raster_height"], orig_sonar.get("waterfall_height"))
        self.assertEqual(export_art["channel_layout"], orig_sonar.get("channel_layout"))
        self.assertEqual(export_art["selected_channels"], orig_sonar.get("channels_included"))
        self.assertEqual(export_art["nadir_pixel_x"], orig_sonar.get("nadir_pixel_x"))
        self.assertEqual(export_art["meters_per_pixel"], orig_sonar.get("meters_per_pixel"))
        self.assertEqual(export_data["analysis"]["sonar_format"], orig_sonar.get("format"))

    # -------------------------------------------------------------------------
    # Test 9: Invalid Analysis ID Handling (404)
    # -------------------------------------------------------------------------
    def test_09_invalid_analysis_id_returns_404(self):
        """Verify 404 response for invalid or non-existent analysis IDs."""
        invalid_id = "non_existent_mission_id_99999"

        r_json = self.client.get(f"/api/v1/analyses/{invalid_id}/export/json")
        self.assertEqual(r_json.status_code, 404)

        r_csv = self.client.get(f"/api/v1/analyses/{invalid_id}/export/csv")
        self.assertEqual(r_csv.status_code, 404)

        r_geojson = self.client.get(f"/api/v1/analyses/{invalid_id}/export/geojson")
        self.assertEqual(r_geojson.status_code, 404)

    # -------------------------------------------------------------------------
    # Test 10: Standard Image Analysis Export (Camera / Non-Sonar)
    # -------------------------------------------------------------------------
    def test_10_standard_image_analysis_export(self):
        """Verify that standard camera/image analyses export cleanly without sonar-only errors."""
        jpeg_bytes = self._create_sample_jpeg_bytes()
        post_resp = self.client.post(
            "/api/v1/analyses/analyze",
            files={"file": ("camera_scan.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
            data={"vessel_lat": 24.8607, "vessel_lon": 67.0011, "vessel_heading_deg": 180.0},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        # 1. JSON export
        resp_json = self.client.get(f"/api/v1/analyses/{analysis_id}/export/json")
        self.assertEqual(resp_json.status_code, 200)
        json_data = resp_json.json()
        self.assertEqual(json_data["analysis"]["analysis_id"], analysis_id)
        self.assertIsNone(json_data["artifact"], "Camera image export must have null sonar artifact")

        # 2. CSV export
        resp_csv = self.client.get(f"/api/v1/analyses/{analysis_id}/export/csv")
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("analysis_id", resp_csv.text)

        # 3. GeoJSON export
        resp_geojson = self.client.get(f"/api/v1/analyses/{analysis_id}/export/geojson")
        self.assertEqual(resp_geojson.status_code, 200)
        self.assertEqual(resp_geojson.json()["type"], "FeatureCollection")

    # -------------------------------------------------------------------------
    # Test 11: Multiple Detections Packaging
    # -------------------------------------------------------------------------
    def test_11_multiple_detections_packaging(self):
        """Verify multiple detections are faithfully packaged across JSON, CSV, and GeoJSON."""
        synthetic_result = {
            "mission_id": "test_multi_det_msn",
            "targets": [
                {
                    "detection_id": "det_01",
                    "class_name": "shipwreck",
                    "display_name": "Shipwreck",
                    "category": "Hazard",
                    "calibrated_confidence": 0.95,
                    "ai_confidence": 0.90,
                    "trust_tier": "VERY_HIGH",
                    "coordinates": {"latitude": 24.861, "longitude": 67.001},
                    "bbox": {"x_min": 10, "y_min": 10, "x_max": 40, "y_max": 40},
                    "dimensions": {"length_m": 20.0, "width_m": 8.0, "height_m": 3.0},
                    "risk_score": 88.0,
                    "risk_tier": "CRITICAL",
                },
                {
                    "detection_id": "det_02",
                    "class_name": "aircraft",
                    "display_name": "Aircraft Debris",
                    "category": "Hazard",
                    "calibrated_confidence": 0.85,
                    "ai_confidence": 0.82,
                    "trust_tier": "HIGH",
                    "coordinates": {"latitude": 24.862, "longitude": 67.002},
                    "bbox": {"x_min": 50, "y_min": 50, "x_max": 70, "y_max": 80},
                    "dimensions": {"length_m": 12.0, "width_m": 6.0, "height_m": 1.5},
                    "risk_score": 72.0,
                    "risk_tier": "HIGH",
                },
                {
                    "detection_id": "det_03",
                    "class_name": "other",
                    "display_name": "Seabed Anomaly",
                    "category": "Anomaly",
                    "calibrated_confidence": 0.60,
                    "ai_confidence": 0.58,
                    "trust_tier": "MODERATE",
                    "coordinates": {"latitude": 24.863, "longitude": 67.003},
                    "bbox": {"x_min": 80, "y_min": 20, "x_max": 95, "y_max": 35},
                    "dimensions": {"length_m": 3.0, "width_m": 2.0, "height_m": 0.8},
                    "risk_score": 35.0,
                    "risk_tier": "LOW",
                },
            ],
        }

        # 1. JSON
        json_export = hydrographic_export_service.export_json(synthetic_result, analysis_id="test_multi_det_msn")
        self.assertEqual(len(json_export["detections"]), 3)
        det_ids = [d["detection_id"] for d in json_export["detections"]]
        self.assertEqual(det_ids, ["det_01", "det_02", "det_03"])

        # 2. CSV
        csv_export = hydrographic_export_service.export_csv(synthetic_result, analysis_id="test_multi_det_msn")
        reader = csv.reader(io.StringIO(csv_export))
        rows = list(reader)
        # 1 header row + 3 detection rows = 4 rows
        self.assertEqual(len(rows), 4)

        # 3. GeoJSON
        geojson_export = hydrographic_export_service.export_geojson(synthetic_result, analysis_id="test_multi_det_msn")
        self.assertEqual(len(geojson_export["features"]), 3)

    # -------------------------------------------------------------------------
    # Test 12: No Cross-Analysis Leakage
    # -------------------------------------------------------------------------
    def test_12_no_cross_analysis_leakage(self):
        """Verify data from analysis A never leaks into export of analysis B."""
        xtf_a = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64, lat=24.111, lon=67.111)
        xtf_b = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64, lat=25.222, lon=68.222)

        resp_a = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("mission_alpha.xtf", io.BytesIO(xtf_a), "application/octet-stream")},
        )
        self.assertEqual(resp_a.status_code, 200)
        id_a = resp_a.json()["mission_id"]

        resp_b = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("mission_bravo.xtf", io.BytesIO(xtf_b), "application/octet-stream")},
        )
        self.assertEqual(resp_b.status_code, 200)
        id_b = resp_b.json()["mission_id"]

        export_a = self.client.get(f"/api/v1/analyses/{id_a}/export/json").json()
        export_b = self.client.get(f"/api/v1/analyses/{id_b}/export/json").json()

        # Analysis IDs strictly isolated
        self.assertEqual(export_a["analysis"]["analysis_id"], id_a)
        self.assertEqual(export_b["analysis"]["analysis_id"], id_b)
        self.assertEqual(export_a["analysis"]["original_filename"], "mission_alpha.xtf")
        self.assertEqual(export_b["analysis"]["original_filename"], "mission_bravo.xtf")

        # Telemetry strictly isolated
        self.assertAlmostEqual(export_a["navigation"]["latitude"], 24.111, places=3)
        self.assertAlmostEqual(export_b["navigation"]["latitude"], 25.222, places=3)

        # Artifact references strictly isolated
        self.assertIn(id_a, export_a["artifact"]["raster_reference"])
        self.assertNotIn(id_b, export_a["artifact"]["raster_reference"])
        self.assertIn(id_b, export_b["artifact"]["raster_reference"])
        self.assertNotIn(id_a, export_b["artifact"]["raster_reference"])

    # -------------------------------------------------------------------------
    # Test 13: OpenAPI Specification Conformance
    # -------------------------------------------------------------------------
    def test_13_openapi_specification(self):
        """Verify all three export endpoints appear in OpenAPI specification with exact media types."""
        from app.core.config import settings

        resp = self.client.get(f"{settings.API_V1_STR}/openapi.json")
        self.assertEqual(resp.status_code, 200)
        spec = resp.json()
        paths = spec.get("paths", {})

        json_ep = "/api/v1/analyses/{analysis_id}/export/json"
        csv_ep = "/api/v1/analyses/{analysis_id}/export/csv"
        geojson_ep = "/api/v1/analyses/{analysis_id}/export/geojson"

        self.assertIn(json_ep, paths)
        self.assertIn(csv_ep, paths)
        self.assertIn(geojson_ep, paths)

        # JSON endpoint content type
        self.assertIn("application/json", paths[json_ep]["get"]["responses"]["200"]["content"])
        # CSV endpoint content type
        self.assertIn("text/csv", paths[csv_ep]["get"]["responses"]["200"]["content"])
        # GeoJSON endpoint content type
        self.assertIn("application/geo+json", paths[geojson_ep]["get"]["responses"]["200"]["content"])


if __name__ == "__main__":
    unittest.main()

