"""
Unit and integration tests for Phase 8: Ping-Level Navigation Track & Geospatial Packaging.

Validates:
1.  Test 1  — XTF ping track extraction & ordering: multi-ping XTF produces ordered track with telemetry.
2.  Test 2  — JSF ping track extraction & ordering: multi-ping JSF produces ordered track with telemetry.
3.  Test 3  — Missing navigation preserves null: unlogged coordinates stay None/null (no 0,0 or Karachi fallback).
4.  Test 4  — Track ordering verification: points strictly match acquisition sequence (Point A -> B -> C).
5.  Test 5  — max_pings bounding consistency: bounded ingestion yields identical ping count in raster & track.
6.  Test 6  — Analysis association & isolation: Analysis A and B have separate, isolated navigation tracks.
7.  Test 7  — GET /sonar/track endpoint: returns 200 with valid SonarNavigationTrack JSON schema.
8.  Test 8  — Invalid analysis ID: GET /sonar/track returns 404 for unknown ID.
9.  Test 9  — Non-sonar analysis: GET /sonar/track returns 404 for standard camera image analyses.
10. Test 10 — Track GeoJSON LineString: GET /export/track.geojson returns RFC 7946 LineString with [lon, lat] order.
11. Test 11 — Track GeoJSON missing coordinates: null coordinates excluded from LineString (never plotted at 0,0).
12. Test 12 — Track CSV formatting: GET /export/track.csv returns valid CSV in ping_index order with empty strings for nulls.
13. Test 13 — Phase 7 export backward compatibility: existing /export/json, /export/csv, /export/geojson function without regressions.
14. Test 14 — Track artifact lifecycle: creation, retrieval, file removal, cleanup, and no internal path leakage.
15. Test 15 — Raster/track count & ordering relationship: track point count equals waterfall height; row i is ping i.
16. Test 16 — OpenAPI specification: all three new endpoints correctly registered in OpenAPI schema.
"""

import csv
import io
import json
import struct
import unittest
from typing import List, Optional, Tuple

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.sonar import SonarNavigationTrack, SonarPingTelemetry
from app.services.master_pipeline_service import master_pipeline_service
from app.services.sonar_artifact_service import sonar_artifact_service
from app.services.sonar_ingestion_service import sonar_ingestion_service
from app.sonar.xtf_reader import (
    XTF_CHAN_INFO_FMT,
    XTF_FILE_HDR_BASE_FMT,
    XTF_HEADER_SONAR,
    XTF_MAGIC_BYTE,
    XTF_PACKET_HDR_FMT,
    XTF_PACKET_MAGIC,
    XTF_PING_CHAN_HDR_FMT,
    XTF_PING_HDR_FMT,
)
from app.tests.test_jsf_parser import build_synthetic_jsf_binary
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


def build_custom_track_xtf(
    coords: List[Tuple[Optional[float], Optional[float]]],
    samples_per_chan: int = 64,
    heading: float = 180.0,
    altitude: float = 15.0,
    depth: float = 25.0,
) -> bytes:
    """
    Builds a synthetic XTF binary with explicit ping-varying coordinates.
    coords is a list of (latitude, longitude) tuples.
    """
    buf = bytearray()
    num_pings = len(coords)

    # 1. Base File Header (256 bytes)
    base_hdr = struct.pack(
        XTF_FILE_HDR_BASE_FMT,
        XTF_MAGIC_BYTE,           # FileFormat (0x7B)
        1,                        # SystemType
        b"TESTPROG",              # RecordingProgramName
        b"1.00",                  # RecordingProgramVersion
        b"SYNTH_SSS",             # SonarName
        1,                        # SonarType
        b"Synthetic Track Test",  # NoteString
        b"test_track.xtf",        # ThisFileName
        1,                        # NavUnits (1 = deg, 0 = meters)
        2,                        # NumberOfSonarChannels
        0,                        # NumberOfBathymetryChannels
        0,                        # NumberOfSnippetChannels
        0,                        # NumberOfForwardLookArrays
        0,                        # NumberOfEchoStrengthChannels
        0,                        # NumberOfInterferometryChannels
        0,                        # Reserved1
        0,                        # Reserved2
        0.0,                      # ReferencePointHeight
        b"\x00" * 12,             # ProjectionType
        b"\x00" * 10,             # SpheroidType
        0,                        # NavigationLatency
        0.0,                      # OriginX
        0.0,                      # OriginY
        0.0, 0.0, 0.0, 0.0,       # NavOffsets (4f)
        0.0, 0.0, 0.0, 0.0,       # MRUOffsets (4f)
        0.0, 0.0,                 # MRUOffsets pitch/roll (2f)
    )
    buf.extend(base_hdr)

    # 2. Channel Info Headers (6 channels x 128 bytes = 768 bytes)
    for ch_idx in range(6):
        ch_type = 1 if ch_idx == 0 else (2 if ch_idx == 1 else 0)
        ch_name = b"Port" if ch_idx == 0 else (b"Starboard" if ch_idx == 1 else b"Unused")
        chan_hdr = struct.pack(
            XTF_CHAN_INFO_FMT,
            ch_type,
            ch_idx,
            0,
            1,
            1,
            1024,
            ch_name.ljust(16, b"\x00"),
            1.0,
            455000.0 if ch_idx < 2 else 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            1,
            8,
            b"\x00" * 53,
        )
        buf.extend(chan_hdr)

    assert len(buf) == 1024, f"Header length must be 1024 bytes, got {len(buf)}"

    # 3. Sonar Ping Packets
    for p_idx, (lat, lon) in enumerate(coords):
        p_samples = samples_per_chan
        chan_data_size = 2 * (64 + p_samples)
        total_pkt_bytes = 14 + 242 + chan_data_size

        pkt_hdr = struct.pack(
            XTF_PACKET_HDR_FMT,
            XTF_PACKET_MAGIC,
            XTF_HEADER_SONAR,
            0,
            2,
            0, 0,
            total_pkt_bytes,
        )
        buf.extend(pkt_hdr)

        eval_y = lat if lat is not None else 0.0
        eval_x = lon if lon is not None else 0.0
        eval_hdg = heading if heading is not None else 0.0
        eval_alt = altitude if altitude is not None else 0.0
        eval_depth = depth if depth is not None else 0.0

        ping_hdr = struct.pack(
            XTF_PING_HDR_FMT,
            2026, 9, 18,          # Year, Month, Day
            12, 0, p_idx, 0,      # Hour, Min, Sec, HSec
            261,                  # JulianDays
            p_idx, p_idx,         # EventNumber, PingNumber
            1500.0, 0.0, 0,       # SoundVelocity, OceanTide, Reserved2
            *(0.0 for _ in range(21)),  # 21 floats
            eval_y, eval_x,       # ShipY, ShipX (double)
            0, 0,                 # ShipAltitude, ShipDepth (h)
            12, 0, p_idx, 0,      # FixTime (4b)
            2.5, 0.0,             # SensorSpeed, KP (f)
            eval_y, eval_x,       # SensorY, SensorX (double)
            0, 0, 0, 0,           # SonarStatus, Range, Bearing, CableOut (4h)
            0.0, 0.0, eval_depth, eval_alt, 0.0,  # Layback, Tension, Depth, Alt, AuxAlt (5f)
            0.0, 0.0, eval_hdg, 0.0, 0.0,          # Pitch, Roll, Heading, Heave, Yaw (5f)
            0, 0.0, 0,            # AttitudeTimeTag, DOT, NavFixMillis
            12, 0, p_idx, 0,      # ComputerClock (4b)
            0, 0, 0, 0,           # DeltaX, DeltaY, ErrorCode, OptionalOffset
            b"\x00" * 7,          # ReservedSpace
        )
        buf.extend(ping_hdr)

        # Channel 0: Port
        port_samples = np.full(p_samples, 50 + p_idx * 5, dtype=np.uint8).tobytes()
        chan0_hdr = struct.pack(
            XTF_PING_CHAN_HDR_FMT,
            0, 0, 50.0, 50.0, 0.0, 0.0, 0.1, 0, 455, 0, 0, 0, 0, 0, 0, 0,
            p_samples, 1, 0.0, 0, 0, 0.0, 0, 0, 0, 0, 0,
        )
        buf.extend(chan0_hdr)
        buf.extend(port_samples)

        # Channel 1: Starboard
        stbd_samples = np.full(p_samples, 80 + p_idx * 5, dtype=np.uint8).tobytes()
        chan1_hdr = struct.pack(
            XTF_PING_CHAN_HDR_FMT,
            1, 0, 50.0, 50.0, 0.0, 0.0, 0.1, 0, 455, 0, 0, 0, 0, 0, 0, 0,
            p_samples, 1, 0.0, 0, 0, 0.0, 0, 0, 0, 0, 0,
        )
        buf.extend(chan1_hdr)
        buf.extend(stbd_samples)

    return bytes(buf)


class TestSonarTrack(unittest.TestCase):
    """
    Test suite for Phase 8: Ping-Level Navigation Track & Geospatial Packaging.
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

    # -------------------------------------------------------------------------
    # Test 1: XTF Ping Track Extraction & Ordering
    # -------------------------------------------------------------------------
    def test_01_xtf_ping_track_extraction_and_ordering(self):
        """
        Verify that an XTF file with multiple pings produces an ordered ping navigation track
        with correct coordinates, timestamps, heading, depth, altitude.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=8,
            samples_per_chan=64,
            lat=24.8607,
            lon=67.0011,
            heading=185.5,
            altitude=14.2,
            depth=22.0,
        )

        ingest_res = sonar_ingestion_service.ingest_sonar(xtf_bytes, filename="transect.xtf")
        self.assertIsNotNone(ingest_res.navigation_track)
        track = ingest_res.navigation_track

        self.assertEqual(track.source_format, "XTF")
        self.assertEqual(track.total_pings, 8)
        self.assertEqual(track.available_navigation_pings, 8)
        self.assertEqual(len(track.points), 8)

        for i, pt in enumerate(track.points):
            self.assertEqual(pt.ping_index, i)
            self.assertEqual(pt.waterfall_row, i)
            self.assertAlmostEqual(pt.latitude, 24.8607, places=4)
            self.assertAlmostEqual(pt.longitude, 67.0011, places=4)
            self.assertAlmostEqual(pt.heading, 185.5, places=1)
            self.assertAlmostEqual(pt.altitude, 14.2, places=1)
            self.assertAlmostEqual(pt.depth, 22.0, places=1)
            self.assertIsNotNone(pt.timestamp)

    # -------------------------------------------------------------------------
    # Test 2: JSF Ping Track Extraction & Ordering
    # -------------------------------------------------------------------------
    def test_02_jsf_ping_track_extraction_and_ordering(self):
        """
        Verify that a JSF file with multiple pings produces an ordered ping navigation track.
        """
        jsf_bytes = build_synthetic_jsf_binary(
            num_pings=6,
            samples_per_chan=64,
            lat=24.8607,
            lon=67.0011,
            heading=90.0,
            altitude=10.0,
            depth=15.0,
        )

        ingest_res = sonar_ingestion_service.ingest_sonar(jsf_bytes, filename="survey.jsf")
        self.assertIsNotNone(ingest_res.navigation_track)
        track = ingest_res.navigation_track

        self.assertEqual(track.source_format, "JSF")
        self.assertEqual(track.total_pings, 6)
        self.assertEqual(track.available_navigation_pings, 6)
        self.assertEqual(len(track.points), 6)

        for i, pt in enumerate(track.points):
            self.assertEqual(pt.ping_index, i)
            self.assertEqual(pt.waterfall_row, i)
            self.assertAlmostEqual(pt.latitude, 24.8607, places=3)
            self.assertAlmostEqual(pt.longitude, 67.0011, places=3)
            self.assertAlmostEqual(pt.heading, 90.0, places=1)

    # -------------------------------------------------------------------------
    # Test 3: Missing Navigation Preserves Null (No 0,0 Fallback)
    # -------------------------------------------------------------------------
    def test_03_missing_navigation_preserves_null(self):
        """
        Verify that pings without coordinates have null/None coordinates — never (0,0),
        never fallback coordinates.
        """
        xtf_bytes = build_synthetic_xtf_binary(
            num_pings=4,
            samples_per_chan=64,
            lat=None,
            lon=None,
            heading=None,
            altitude=None,
            depth=None,
        )

        ingest_res = sonar_ingestion_service.ingest_sonar(xtf_bytes, filename="nonav.xtf")
        track = ingest_res.navigation_track
        self.assertIsNotNone(track)
        self.assertEqual(track.total_pings, 4)
        self.assertEqual(track.available_navigation_pings, 0)

        for pt in track.points:
            self.assertIsNone(pt.latitude)
            self.assertIsNone(pt.longitude)
            self.assertIsNone(pt.heading)
            self.assertIsNone(pt.altitude)
            self.assertIsNone(pt.depth)

    # -------------------------------------------------------------------------
    # Test 4: Track Ordering Verification (Sequential Coordinates A -> B -> C)
    # -------------------------------------------------------------------------
    def test_04_track_ordering_verification(self):
        """
        Ping records strictly match acquisition order (0, 1, 2, ...).
        Verified through sequential synthetic coordinates (Point A -> Point B -> Point C).
        """
        coords = [
            (24.8500, 67.0000),  # Point A
            (24.8550, 67.0050),  # Point B
            (24.8600, 67.0100),  # Point C
            (24.8650, 67.0150),  # Point D
        ]
        xtf_bytes = build_custom_track_xtf(coords)

        ingest_res = sonar_ingestion_service.ingest_sonar(xtf_bytes, filename="ordered.xtf")
        track = ingest_res.navigation_track
        self.assertIsNotNone(track)
        self.assertEqual(len(track.points), 4)

        for i, (expected_lat, expected_lon) in enumerate(coords):
            pt = track.points[i]
            self.assertEqual(pt.ping_index, i)
            self.assertEqual(pt.waterfall_row, i)
            self.assertAlmostEqual(pt.latitude, expected_lat, places=4)
            self.assertAlmostEqual(pt.longitude, expected_lon, places=4)

    # -------------------------------------------------------------------------
    # Test 5: max_pings Bounding Consistency
    # -------------------------------------------------------------------------
    def test_05_max_pings_bounding_consistency(self):
        """
        When max_pings is specified, the navigation track and the waterfall raster
        describe the identical ping window (N pings in both).
        """
        coords = [(24.85 + i * 0.001, 67.00 + i * 0.001) for i in range(12)]
        xtf_bytes = build_custom_track_xtf(coords)

        ingest_res = sonar_ingestion_service.ingest_sonar(xtf_bytes, max_pings=5, filename="bounded.xtf")
        self.assertEqual(ingest_res.waterfall_raster.shape[0], 5)
        self.assertIsNotNone(ingest_res.navigation_track)
        self.assertEqual(ingest_res.navigation_track.total_pings, 5)
        self.assertEqual(len(ingest_res.navigation_track.points), 5)
        # Point 4 corresponds to index 4
        self.assertEqual(ingest_res.navigation_track.points[4].ping_index, 4)

    # -------------------------------------------------------------------------
    # Test 6: Analysis Association & Isolation
    # -------------------------------------------------------------------------
    def test_06_analysis_association_and_isolation(self):
        """
        Analysis A and Analysis B have completely separate, isolated navigation tracks.
        """
        coords_A = [(24.86, 67.00), (24.87, 67.01)]
        coords_B = [(-33.86, 151.20), (-33.87, 151.21), (-33.88, 151.22)]

        xtf_A = build_custom_track_xtf(coords_A)
        xtf_B = build_custom_track_xtf(coords_B)

        resp_A = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("mission_A.xtf", xtf_A, "application/octet-stream")},
        )
        self.assertEqual(resp_A.status_code, 200)
        id_A = resp_A.json()["mission_id"]

        resp_B = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("mission_B.xtf", xtf_B, "application/octet-stream")},
        )
        self.assertEqual(resp_B.status_code, 200)
        id_B = resp_B.json()["mission_id"]

        self.assertNotEqual(id_A, id_B)

        # Query tracks for both
        track_resp_A = self.client.get(f"/api/v1/analyses/{id_A}/sonar/track")
        self.assertEqual(track_resp_A.status_code, 200)
        track_data_A = track_resp_A.json()
        self.assertEqual(track_data_A["analysis_id"], id_A)
        self.assertEqual(track_data_A["total_pings"], 2)
        self.assertAlmostEqual(track_data_A["points"][0]["latitude"], 24.86, places=2)

        track_resp_B = self.client.get(f"/api/v1/analyses/{id_B}/sonar/track")
        self.assertEqual(track_resp_B.status_code, 200)
        track_data_B = track_resp_B.json()
        self.assertEqual(track_data_B["analysis_id"], id_B)
        self.assertEqual(track_data_B["total_pings"], 3)
        self.assertAlmostEqual(track_data_B["points"][0]["latitude"], -33.86, places=2)

    # -------------------------------------------------------------------------
    # Test 7: GET /sonar/track Endpoint
    # -------------------------------------------------------------------------
    def test_07_get_sonar_track_endpoint(self):
        """
        Returns 200 with valid SonarNavigationTrack schema, correct analysis_id,
        total_pings, and ordered points.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=7, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("survey7.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        a_id = post_resp.json()["mission_id"]

        resp = self.client.get(f"/api/v1/analyses/{a_id}/sonar/track")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/json", resp.headers["content-type"])

        data = resp.json()
        track = SonarNavigationTrack.model_validate(data)
        self.assertEqual(track.analysis_id, a_id)
        self.assertEqual(track.total_pings, 7)
        self.assertEqual(len(track.points), 7)
        self.assertEqual([p.ping_index for p in track.points], list(range(7)))

    # -------------------------------------------------------------------------
    # Test 8: Invalid Analysis ID Returns 404
    # -------------------------------------------------------------------------
    def test_08_invalid_analysis_id_returns_404(self):
        """
        GET /sonar/track with non-existent ID returns 404.
        """
        resp = self.client.get("/api/v1/analyses/msn_nonexistent_xyz999/sonar/track")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 9: Non-Sonar Analysis Returns 404
    # -------------------------------------------------------------------------
    def test_09_non_sonar_analysis_returns_404(self):
        """
        Querying /sonar/track for an image (PNG/JPG) analysis returns 404.
        """
        img_bytes = self._create_sample_jpeg_bytes()
        post_resp = self.client.post(
            "/api/v1/analyses/analyze",
            files={"file": ("camera_photo.jpg", img_bytes, "image/jpeg")},
        )
        self.assertEqual(post_resp.status_code, 200)
        photo_id = post_resp.json()["mission_id"]

        resp = self.client.get(f"/api/v1/analyses/{photo_id}/sonar/track")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("sonar", resp.json()["detail"].lower())

    # -------------------------------------------------------------------------
    # Test 10: Track GeoJSON LineString & [lon, lat] Order
    # -------------------------------------------------------------------------
    def test_10_track_geojson_linestring(self):
        """
        GET /export/track.geojson returns valid RFC 7946 GeoJSON FeatureCollection
        with a LineString geometry and coordinates in strictly [longitude, latitude] order.
        """
        coords = [
            (24.8601, 67.0011),
            (24.8605, 67.0015),
            (24.8610, 67.0020),
        ]
        xtf_bytes = build_custom_track_xtf(coords)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("geojson_track.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        a_id = post_resp.json()["mission_id"]

        resp = self.client.get(f"/api/v1/analyses/{a_id}/export/track.geojson")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("geo+json", resp.headers["content-type"])
        self.assertIn(f'filename="marinescan_{a_id}_track.geojson"', resp.headers["content-disposition"])

        geojson = resp.json()
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["analysis_id"], a_id)
        self.assertEqual(len(geojson["features"]), 1)

        feat = geojson["features"][0]
        self.assertEqual(feat["type"], "Feature")
        self.assertEqual(feat["geometry"]["type"], "LineString")

        # RFC 7946: [longitude, latitude]
        geom_coords = feat["geometry"]["coordinates"]
        self.assertEqual(len(geom_coords), 3)
        for idx, (expected_lat, expected_lon) in enumerate(coords):
            lon_got, lat_got = geom_coords[idx]
            self.assertAlmostEqual(lon_got, expected_lon, places=4)
            self.assertAlmostEqual(lat_got, expected_lat, places=4)

        props = feat["properties"]
        self.assertEqual(props["analysis_id"], a_id)
        self.assertEqual(props["source_format"], "XTF")
        self.assertEqual(props["total_pings"], 3)
        self.assertEqual(props["available_navigation_pings"], 3)

    # -------------------------------------------------------------------------
    # Test 11: Track GeoJSON Missing Coordinates Excluded (No 0,0)
    # -------------------------------------------------------------------------
    def test_11_track_geojson_missing_coordinates(self):
        """
        Pings with null coordinates are excluded from the GeoJSON LineString
        rather than plotted at (0, 0).
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=5, samples_per_chan=64, lat=None, lon=None)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("null_track.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        a_id = post_resp.json()["mission_id"]

        resp = self.client.get(f"/api/v1/analyses/{a_id}/export/track.geojson")
        self.assertEqual(resp.status_code, 200)
        geojson = resp.json()

        # When 0 valid navigation points exist, features list must be empty
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["features"], [])

    # -------------------------------------------------------------------------
    # Test 12: Track CSV Formatting & Ordering
    # -------------------------------------------------------------------------
    def test_12_track_csv_formatting(self):
        """
        GET /export/track.csv returns valid CSV with correct headers, correct column ordering,
        empty strings for missing values, and rows ordered by ping_index.
        """
        coords = [
            (24.8601, 67.0011),
            (None, None),
            (24.8610, 67.0020),
        ]
        xtf_bytes = build_custom_track_xtf(coords)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("csv_track.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        a_id = post_resp.json()["mission_id"]

        resp = self.client.get(f"/api/v1/analyses/{a_id}/export/track.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers["content-type"])
        self.assertIn(f'filename="marinescan_{a_id}_track.csv"', resp.headers["content-disposition"])

        csv_reader = list(csv.reader(io.StringIO(resp.text)))
        self.assertEqual(
            csv_reader[0],
            ["analysis_id", "ping_index", "timestamp", "latitude", "longitude", "heading", "depth", "altitude"],
        )
        # 3 data rows
        self.assertEqual(len(csv_reader), 4)

        # Row 0: has coords
        row0 = csv_reader[1]
        self.assertEqual(row0[0], a_id)
        self.assertEqual(row0[1], "0")
        self.assertTrue(len(row0[3]) > 0)  # lat
        self.assertTrue(len(row0[4]) > 0)  # lon

        # Row 1: null coords rendered as empty strings
        row1 = csv_reader[2]
        self.assertEqual(row1[0], a_id)
        self.assertEqual(row1[1], "1")
        self.assertEqual(row1[3], "")  # lat is empty string, NOT "0.0"
        self.assertEqual(row1[4], "")  # lon is empty string, NOT "0.0"

        # Row 2: has coords
        row2 = csv_reader[3]
        self.assertEqual(row2[1], "2")

    # -------------------------------------------------------------------------
    # Test 13: Phase 7 Export Backward Compatibility
    # -------------------------------------------------------------------------
    def test_13_phase_7_export_backward_compatibility(self):
        """
        Existing /export/json, /export/csv, and /export/geojson continue to function
        identically with no regressions, and JSON export includes track references.
        """
        xtf_bytes = build_synthetic_xtf_binary(num_pings=4, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("compat.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        a_id = post_resp.json()["mission_id"]

        # Phase 7 JSON export
        resp_json = self.client.get(f"/api/v1/analyses/{a_id}/export/json")
        self.assertEqual(resp_json.status_code, 200)
        json_data = resp_json.json()
        self.assertIn("analysis", json_data)
        self.assertEqual(json_data["analysis"]["analysis_id"], a_id)
        self.assertIn("artifact", json_data)
        self.assertEqual(
            json_data["artifact"].get("track_reference"),
            f"/api/v1/analyses/{a_id}/sonar/track",
        )
        self.assertEqual(
            json_data["artifact"].get("track_artifact_id"),
            f"track_{a_id}",
        )

        # Phase 7 Detection CSV export
        resp_csv = self.client.get(f"/api/v1/analyses/{a_id}/export/csv")
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn("text/csv", resp_csv.headers["content-type"])

        # Phase 7 Detection GeoJSON export
        resp_geojson = self.client.get(f"/api/v1/analyses/{a_id}/export/geojson")
        self.assertEqual(resp_geojson.status_code, 200)
        self.assertEqual(resp_geojson.json()["type"], "FeatureCollection")

    # -------------------------------------------------------------------------
    # Test 14: Track Artifact Lifecycle
    # -------------------------------------------------------------------------
    def test_14_track_artifact_lifecycle(self):
        """
        Track artifact is created on analysis, retrievable, deleted on cleanup,
        and handles missing file cleanly without internal path leakage.
        """
        dummy_track = SonarNavigationTrack(
            analysis_id="test_lifecycle_123",
            source_format="XTF",
            total_pings=2,
            available_navigation_pings=2,
            points=[
                SonarPingTelemetry(ping_index=0, waterfall_row=0, latitude=10.0, longitude=20.0),
                SonarPingTelemetry(ping_index=1, waterfall_row=1, latitude=10.1, longitude=20.1),
            ],
        )

        # Save track
        saved_meta = sonar_artifact_service.save_track_artifact("test_lifecycle_123", dummy_track)
        self.assertEqual(saved_meta["artifact_id"], "track_test_lifecycle_123")
        self.assertTrue(sonar_artifact_service.has_track_artifact("test_lifecycle_123"))

        # Retrieve track
        retrieved = sonar_artifact_service.get_track_artifact("test_lifecycle_123")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["analysis_id"], "test_lifecycle_123")
        self.assertEqual(len(retrieved["points"]), 2)

        # Check that no server local filesystem path is leaked in retrieved dict
        retrieved_str = json.dumps(retrieved)
        self.assertNotIn("/Users/", retrieved_str)
        self.assertNotIn(".cache", retrieved_str)

        # Delete artifact
        sonar_artifact_service.delete_artifact("test_lifecycle_123")
        self.assertFalse(sonar_artifact_service.has_track_artifact("test_lifecycle_123"))
        self.assertIsNone(sonar_artifact_service.get_track_artifact("test_lifecycle_123"))

    # -------------------------------------------------------------------------
    # Test 15: Raster / Track Count & Ordering Relationship
    # -------------------------------------------------------------------------
    def test_15_raster_track_count_and_ordering_relationship(self):
        """
        Verified that track point count equals raster height (N pings = N rows)
        and that track point i corresponds to waterfall row i.
        """
        coords = [(24.86 + i * 0.002, 67.00 + i * 0.002) for i in range(10)]
        xtf_bytes = build_custom_track_xtf(coords)

        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("relationship.xtf", xtf_bytes, "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        data = post_resp.json()
        a_id = data["mission_id"]
        sonar_meta = data["sonar"]

        # Waterfall height is 10
        self.assertEqual(sonar_meta["waterfall_height"], 10)
        self.assertEqual(sonar_meta["total_pings"], 10)

        # Track point count is 10
        track_resp = self.client.get(f"/api/v1/analyses/{a_id}/sonar/track")
        self.assertEqual(track_resp.status_code, 200)
        track_data = track_resp.json()

        self.assertEqual(track_data["total_pings"], 10)
        self.assertEqual(len(track_data["points"]), 10)

        for i in range(10):
            pt = track_data["points"][i]
            self.assertEqual(pt["waterfall_row"], i)
            self.assertEqual(pt["ping_index"], i)
            self.assertAlmostEqual(pt["latitude"], coords[i][0], places=4)
            self.assertAlmostEqual(pt["longitude"], coords[i][1], places=4)

    # -------------------------------------------------------------------------
    # Test 16: OpenAPI Specification Registration
    # -------------------------------------------------------------------------
    def test_16_openapi_specification(self):
        """
        Verify new endpoints appear in /api/v1/openapi.json with correct paths, methods, and tags.
        """
        resp = self.client.get("/api/v1/openapi.json")
        self.assertEqual(resp.status_code, 200)
        schema = resp.json()
        paths = schema.get("paths", {})

        # Verify track endpoint
        track_path = "/api/v1/analyses/{analysis_id}/sonar/track"
        self.assertIn(track_path, paths)
        self.assertIn("get", paths[track_path])

        # Verify GeoJSON track export endpoint
        geojson_track_path = "/api/v1/analyses/{analysis_id}/export/track.geojson"
        self.assertIn(geojson_track_path, paths)
        self.assertIn("get", paths[geojson_track_path])

        # Verify CSV track export endpoint
        csv_track_path = "/api/v1/analyses/{analysis_id}/export/track.csv"
        self.assertIn(csv_track_path, paths)
        self.assertIn("get", paths[csv_track_path])


if __name__ == "__main__":
    unittest.main()
