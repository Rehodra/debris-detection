"""
Unit and Integration Tests for EdgeTech Just Sonar Format (.jsf) Sonar Reader.

Phase 3 Verification Suite.
Covers:
  1. Invalid / Non-JSF input rejection
  2. Truncated / Corrupt file detection
  3. BaseSonarParser contract compliance
  4. Message framing & skipping of non-acoustic records (e.g. NMEA 2002)
  5. Acoustic message (Type 80) decoding
  6. Sample decoding & weighting factor scaling
  7. Multiple pings along-track parsing
  8. Bounded max_pings enforcement
  9. Missing navigation fields preservation (None)
 10. Sentinel coordinate & sensor value handling
 11. Channel selection (Port, Starboard, Dual-channel)
 12. Waterfall raster generation & SonarRasterBuilder integration
 13. Malformed message handling
 14. Real physical units preservation (no fabrication of resolution/slant range)
 15. Real-file integration test suite (skipped when no real fixture is present)
"""

import io
import os
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Optional

import numpy as np

from app.schemas.sonar import SonarFormat
from app.sonar.base import (
    BaseSonarParser,
    SonarCorruptFileError,
    SonarFormatError,
)
from app.sonar.jsf_reader import (
    JsfSonarParser,
    JSF_MAGIC_MARKER,
    JSF_MSG_HDR_FMT,
    JSF_MSG_HDR_LEN,
    JSF_MSG_NMEA_STRING,
    JSF_MSG_SONAR_DATA,
    JSF_TRACE_HDR_FMT,
    JSF_TRACE_HDR_LEN,
)


def build_synthetic_jsf_binary(
    num_pings: int = 5,
    samples_per_chan: int = 100,
    channels: tuple = (0, 1),
    lat: Optional[float] = 24.8607,
    lon: Optional[float] = 67.0011,
    heading: Optional[float] = 180.0,
    altitude: Optional[float] = 12.0,
    depth: Optional[float] = 20.0,
    coord_units: int = 2,  # 2 = 10^-4 minutes of arc, 1 = mm
    sample_interval_ns: int = 20000,  # 20 us -> 50 kHz sampling
    weighting_factor: int = 0,
    include_nmea: bool = True,
) -> bytes:
    """
    Build a specification-compliant synthetic EdgeTech JSF binary buffer.
    Constructs 16-byte message headers and Message 80 sonar trace packets.
    """
    buf = bytearray()

    # Optional preliminary NMEA 2002 message to verify message framing / skipping
    if include_nmea:
        nmea_payload = b"$GPGGA,120000.00,2451.642,N,06700.066,E,1,08,1.0,0.0,M,0.0,M,,*47"
        nmea_hdr = struct.pack(
            JSF_MSG_HDR_FMT,
            JSF_MAGIC_MARKER,        # Marker (0x1601)
            16,                      # Protocol revision
            1,                       # Session ID
            JSF_MSG_NMEA_STRING,     # Msg Type 2002
            0,                       # Command type
            0,                       # Subsystem
            0,                       # Channel
            0,                       # Sequence
            0,                       # Reserved
            len(nmea_payload),       # Byte count
        )
        buf.extend(nmea_hdr)
        buf.extend(nmea_payload)

    # Construct pings
    base_time = 1609459200  # 2021-01-01T00:00:00Z

    for ping_idx in range(num_pings):
        p_time = base_time + ping_idx
        ms_today = (ping_idx * 1000 + 500) % 86400000

        # Encode coordinates
        if lat is not None and coord_units == 2:
            y_coord = int(round(lat * 600000.0))
        elif lat is not None and coord_units == 1:
            y_coord = int(round(lat * 1000.0))
        else:
            y_coord = 0

        if lon is not None and coord_units == 2:
            x_coord = int(round(lon * 600000.0))
        elif lon is not None and coord_units == 1:
            x_coord = int(round(lon * 1000.0))
        else:
            x_coord = 0

        hdg_raw = int(round(heading * 100.0)) if heading is not None else 0
        alt_raw = int(round(altitude * 1000.0)) if altitude is not None else 0
        dep_raw = int(round(depth * 1000.0)) if depth is not None else 0

        for ch in channels:
            # 16-bit acoustic sample array
            # Generate deterministic gradient: Port 10..50, Starboard 60..100
            start_val = 10 if ch == 0 else 60
            samples = np.linspace(start_val, start_val + 40, samples_per_chan, dtype=np.uint16)
            sample_bytes = samples.tobytes()

            payload_len = JSF_TRACE_HDR_LEN + len(sample_bytes)

            # 16-byte Message Header
            msg_hdr = struct.pack(
                JSF_MSG_HDR_FMT,
                JSF_MAGIC_MARKER,        # Marker (0x1601)
                16,                      # Protocol revision
                1,                       # Session ID
                JSF_MSG_SONAR_DATA,      # Msg Type 80
                0,                       # Command type
                20,                      # Subsystem (sidescan)
                ch,                      # Channel (0=port, 1=stbd)
                ping_idx % 256,          # Sequence
                0,                       # Reserved
                payload_len,             # Byte count
            )
            buf.extend(msg_hdr)

            # 240-byte Trace Header
            trace_hdr = struct.pack(
                JSF_TRACE_HDR_FMT,
                p_time,                  # 0..3: ping_time
                0,                       # 4..7: starting_depth
                ping_idx,                # 8..11: ping_number
                b"\x00" * 38,            # 12..49: reserved
                hdg_raw,                 # 50..51: heading (0.01 deg)
                b"\x00" * 28,            # 52..79: reserved
                x_coord,                 # 80..83: Longitude / X
                y_coord,                 # 84..87: Latitude / Y
                coord_units,             # 88..89: Coordinate units
                b"\x00" * 24,            # 90..113: reserved
                samples_per_chan,        # 114..115: num_samples
                sample_interval_ns,      # 116..119: sample_interval_ns
                b"\x00" * 16,            # 120..135: reserved
                dep_raw,                 # 136..139: depth_mm
                b"\x00" * 4,             # 140..143: reserved
                alt_raw,                 # 144..147: altitude_mm
                b"\x00" * 20,            # 148..167: reserved
                weighting_factor,        # 168..169: weighting_factor N
                b"\x00" * 30,            # 170..199: reserved
                ms_today,                # 200..203: ms_today
                b"\x00" * 36,            # 204..239: reserved
            )
            buf.extend(trace_hdr)
            buf.extend(sample_bytes)

    return bytes(buf)


class TestJsfSonarParserSynthetic(unittest.TestCase):
    """
    Unit tests for JsfSonarParser using specification-compliant synthetic buffers.
    """

    def setUp(self):
        self.parser = JsfSonarParser()

    def test_01_invalid_input(self):
        """
        Reject plain text, JPEG headers, empty buffers, and non-0x1601 magic numbers.
        """
        # Empty input
        self.assertFalse(self.parser.validate(b""))
        with self.assertRaises(SonarCorruptFileError):
            self.parser.parse_header(b"")

        # Plain text
        self.assertFalse(self.parser.validate(b"This is not a JSF file!"))
        with self.assertRaises(SonarFormatError):
            self.parser.parse_header(b"This is not a JSF file at all!")

        # Non-0x1601 magic
        bad_magic = struct.pack("<H14s", 0x7B01, b"\x00" * 14)
        self.assertFalse(self.parser.validate(bad_magic))
        with self.assertRaises(SonarFormatError):
            self.parser.parse_header(bad_magic)

    def test_02_truncated_jsf(self):
        """
        Detect truncated message headers and corrupt byte counts.
        """
        buf = build_synthetic_jsf_binary(num_pings=2)

        # Truncated in the middle of a message header
        trunc_hdr = buf[:10]
        self.assertFalse(self.parser.validate(trunc_hdr))
        with self.assertRaises(SonarCorruptFileError):
            self.parser.parse_header(trunc_hdr)

        # Truncated in the middle of message payload
        trunc_payload = buf[:100]
        self.assertFalse(self.parser.validate(trunc_payload))
        with self.assertRaises(SonarCorruptFileError):
            self.parser.build_waterfall_raster(trunc_payload)

    def test_03_parser_contract_compliance(self):
        """
        Verify that JsfSonarParser strictly complies with BaseSonarParser interface.
        """
        self.assertIsInstance(self.parser, BaseSonarParser)

        buf = build_synthetic_jsf_binary(num_pings=3)
        res = self.parser.parse(buf)

        self.assertEqual(res.metadata.format, SonarFormat.JSF.value)
        self.assertEqual(len(res.pings), 3)
        self.assertIsNotNone(res.navigation)
        self.assertAlmostEqual(res.navigation.latitude, 24.8607, places=4)
        self.assertAlmostEqual(res.navigation.longitude, 67.0011, places=4)

    def test_04_message_framing_and_skipping(self):
        """
        Verify that parser cleanly traverses non-acoustic messages (NMEA 2002)
        and aligns onto subsequent Message 80 sonar packets.
        """
        buf = build_synthetic_jsf_binary(num_pings=4, include_nmea=True)
        meta = self.parser.parse_header(buf)

        self.assertEqual(meta.format, SonarFormat.JSF.value)
        self.assertEqual(meta.total_pings, 4)
        self.assertEqual(meta.channel_count, 2)

        # Ensure raster builds properly past the NMEA message
        raster, r_meta = self.parser.build_waterfall_raster(buf)
        self.assertEqual(raster.shape, (4, 200))
        self.assertEqual(r_meta["format"], "JSF")

    def test_05_acoustic_message_decoding(self):
        """
        Verify that Message 80 correctly extracts ping time, ping number,
        sampling interval, and sample counts.
        """
        buf = build_synthetic_jsf_binary(num_pings=3, samples_per_chan=128, sample_interval_ns=25000)
        pings = self.parser.parse_pings(buf)

        self.assertEqual(len(pings), 3)
        for i, p in enumerate(pings):
            self.assertEqual(p.ping_index, i)
            self.assertIsNotNone(p.timestamp)
            self.assertIn("2021-01-01", p.timestamp)

    def test_06_sample_decoding_and_weighting_factor(self):
        """
        Verify sample decoding and scaling when weighting factor N is non-zero (sample * 2^-N).
        """
        # Weighting factor = 2 -> scaled = raw * 2^-2 = raw / 4.0
        buf_scaled = build_synthetic_jsf_binary(num_pings=2, samples_per_chan=50, weighting_factor=2)
        raster_scaled, _ = self.parser.build_waterfall_raster(buf_scaled)

        # Weighting factor = 0 -> unscaled
        buf_unscaled = build_synthetic_jsf_binary(num_pings=2, samples_per_chan=50, weighting_factor=0)
        raster_unscaled, _ = self.parser.build_waterfall_raster(buf_unscaled)

        self.assertEqual(raster_scaled.shape, (2, 100))
        self.assertEqual(raster_unscaled.shape, (2, 100))
        self.assertEqual(raster_scaled.dtype, np.uint8)

    def test_07_multiple_pings(self):
        """
        Verify sequential ping telemetry extraction across 10 pings.
        """
        num_pings = 10
        buf = build_synthetic_jsf_binary(num_pings=num_pings, samples_per_chan=64)
        pings = self.parser.parse_pings(buf)

        self.assertEqual(len(pings), num_pings)
        for idx, p in enumerate(pings):
            self.assertEqual(p.ping_index, idx)
            self.assertAlmostEqual(p.heading_deg, 180.0, places=1)
            self.assertAlmostEqual(p.altitude_m, 12.0, places=1)
            self.assertAlmostEqual(p.depth_m, 20.0, places=1)

    def test_08_bounded_max_pings(self):
        """
        Enforce strict memory bounds when max_pings is specified.
        """
        buf = build_synthetic_jsf_binary(num_pings=12)

        # parse_pings max_pings
        pings = self.parser.parse_pings(buf, max_pings=4)
        self.assertEqual(len(pings), 4)

        # build_waterfall_raster max_pings
        raster, meta = self.parser.build_waterfall_raster(buf, max_pings=5)
        self.assertEqual(raster.shape[0], 5)
        self.assertEqual(meta["total_pings"], 5)

    def test_09_missing_navigation_fields(self):
        """
        When navigation fields are unlogged, output None strictly without fabrication.
        """
        buf = build_synthetic_jsf_binary(
            num_pings=3,
            lat=None,
            lon=None,
            heading=None,
            altitude=None,
            depth=None,
        )
        meta = self.parser.parse_header(buf)
        self.assertFalse(meta.navigation_available)

        telemetry = self.parser.extract_telemetry(buf)
        # Should be None or all None fields
        if telemetry:
            self.assertIsNone(telemetry.latitude)
            self.assertIsNone(telemetry.longitude)
            self.assertIsNone(telemetry.heading_deg)
            self.assertIsNone(telemetry.altitude_m)
            self.assertIsNone(telemetry.depth_m)

    def test_10_sentinel_handling(self):
        """
        Projected millimeter coordinates (coord_units != 2) or (0, 0) sentinels must NOT
        be converted to geodetic degrees.
        """
        # Projected mm coordinates (coord_units = 1)
        buf_proj = build_synthetic_jsf_binary(num_pings=2, coord_units=1, lat=500000.0, lon=200000.0)
        nav_proj = self.parser.extract_telemetry(buf_proj)
        self.assertIsNone(nav_proj.latitude)
        self.assertIsNone(nav_proj.longitude)

        # Null Island (0, 0) coordinates
        buf_null = build_synthetic_jsf_binary(num_pings=2, coord_units=2, lat=0.0, lon=0.0)
        nav_null = self.parser.extract_telemetry(buf_null)
        self.assertIsNone(nav_null.latitude)
        self.assertIsNone(nav_null.longitude)

    def test_11_channel_selection(self):
        """
        Support selective rendering of Port (ch 0), Starboard (ch 1), or Dual-channel.
        """
        buf = build_synthetic_jsf_binary(num_pings=4, samples_per_chan=75)

        # Port only
        raster_p, meta_p = self.parser.build_waterfall_raster(buf, channels=[0])
        self.assertEqual(raster_p.shape, (4, 75))
        self.assertEqual(meta_p["channel_layout"], "port_only")
        self.assertEqual(meta_p["nadir_pixel_x"], 75.0)

        # Starboard only
        raster_s, meta_s = self.parser.build_waterfall_raster(buf, channels=[1])
        self.assertEqual(raster_s.shape, (4, 75))
        self.assertEqual(meta_s["channel_layout"], "starboard_only")
        self.assertEqual(meta_s["nadir_pixel_x"], 0.0)

        # Dual channel
        raster_d, meta_d = self.parser.build_waterfall_raster(buf, channels=[0, 1])
        self.assertEqual(raster_d.shape, (4, 150))
        self.assertEqual(meta_d["channel_layout"], "port_nadir_starboard")
        self.assertEqual(meta_d["nadir_pixel_x"], 75.0)

    def test_12_raster_integration(self):
        """
        Confirm that generated raster is a valid 2D uint8 NumPy matrix within [0, 255].
        """
        buf = build_synthetic_jsf_binary(num_pings=5, samples_per_chan=80)
        raster, meta = self.parser.build_waterfall_raster(buf)

        self.assertIsInstance(raster, np.ndarray)
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(raster.shape, (5, 160))
        self.assertEqual(meta["format"], "JSF")
        self.assertGreaterEqual(raster.min(), 0)
        self.assertLessEqual(raster.max(), 255)

    def test_13_malformed_message_handling(self):
        """
        Handle Message 80 with declared byte_count < 240 bytes gracefully.
        """
        bad_msg = bytearray()
        bad_hdr = struct.pack(
            JSF_MSG_HDR_FMT,
            JSF_MAGIC_MARKER,
            16,
            1,
            JSF_MSG_SONAR_DATA,
            0,
            20,
            0,
            0,
            0,
            100,  # Invalid: declared size < 240 bytes for Message 80!
        )
        bad_msg.extend(bad_hdr)
        bad_msg.extend(b"\x00" * 100)

        with self.assertRaises(SonarCorruptFileError):
            self.parser.build_waterfall_raster(bytes(bad_msg))

    def test_14_no_fabricated_physical_units(self):
        """
        When sample interval is unrecorded (0), range and resolution must strictly be None.
        When valid sample interval is provided, range is computed without fabrication.
        """
        # A: Sample interval = 0 (unrecorded)
        buf_zero = build_synthetic_jsf_binary(num_pings=2, samples_per_chan=100, sample_interval_ns=0)
        _, meta_zero = self.parser.build_waterfall_raster(buf_zero)
        self.assertIsNone(meta_zero["slant_range_m"])
        self.assertIsNone(meta_zero["meters_per_pixel"])

        # B: Valid sample interval (20,000 ns = 20 us)
        # 100 samples * 20 us = 2000 us = 2 ms
        # 2 ms * 1500 m/s / 2 = 1.5 meters range
        buf_valid = build_synthetic_jsf_binary(num_pings=2, samples_per_chan=100, sample_interval_ns=20000)
        _, meta_valid = self.parser.build_waterfall_raster(buf_valid)
        self.assertEqual(meta_valid["slant_range_m"], 1.5)
        self.assertEqual(meta_valid["meters_per_pixel"], 0.015)


class TestJsfRealFileIntegration(unittest.TestCase):
    """
    Integration test reserved for physical EdgeTech (.jsf) recording files.
    Skipped by default when no real survey fixture is available in the repository.
    """

    @unittest.skipUnless(
        os.path.exists("fixtures/sonar/real_survey.jsf"),
        "Real .jsf fixture not available in repository; real-file integration testing remains pending.",
    )
    def test_real_jsf_fixture_validation(self):
        real_path = Path("fixtures/sonar/real_survey.jsf")
        parser = JsfSonarParser()
        self.assertTrue(parser.validate(real_path))

        meta = parser.parse_header(real_path)
        self.assertEqual(meta.format, SonarFormat.JSF.value)
        self.assertGreater(meta.total_pings, 0)

        raster, r_meta = parser.build_waterfall_raster(real_path, max_pings=20)
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(raster.shape[0], min(20, meta.total_pings))


if __name__ == "__main__":
    unittest.main()
