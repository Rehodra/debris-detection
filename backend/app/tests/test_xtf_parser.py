"""
Unit and Integration Tests for Extended Triton Format (.xtf) Sonar Reader.

Covers:
  1. Invalid / Non-XTF input rejection
  2. Truncated / Corrupt file detection
  3. BaseSonarParser contract compliance
  4. Missing navigation fields preservation (None)
  5. Sentinel coordinate / value handling
  6. Bounded max_pings enforcement
  7. Channel selection (Port, Starboard, Subbottom)
  8. Varying sample length alignment
  9. Waterfall raster generation and dynamic range normalization
 10. Verification that GPS is never fabricated
 11. Real-file integration test suite (skipped when no real fixture is present)
"""

import os
import struct
import tempfile
import unittest
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.schemas.sonar import SonarFormat
from app.sonar.base import (
    BaseSonarParser,
    SonarCorruptFileError,
    SonarFormatError,
)
from app.sonar.xtf_reader import (
    XtfSonarParser,
    XTF_CHAN_INFO_FMT,
    XTF_FILE_HDR_BASE_FMT,
    XTF_HEADER_SONAR,
    XTF_MAGIC_BYTE,
    XTF_PACKET_HDR_FMT,
    XTF_PACKET_MAGIC,
    XTF_PING_CHAN_HDR_FMT,
    XTF_PING_HDR_FMT,
)


def build_synthetic_xtf_binary(
    num_pings: int = 5,
    samples_per_chan: int = 100,
    nav_units: int = 1,  # 1 = Degrees, 0 = Meters
    lat: Optional[float] = 24.8607,
    lon: Optional[float] = 67.0011,
    heading: Optional[float] = 180.0,
    altitude: Optional[float] = 15.0,
    depth: Optional[float] = 25.0,
    varying_lengths: bool = False,
) -> bytes:
    """
    Build a specification-compliant synthetic XTF binary buffer.
    Matches Triton XTF 1024-byte file header and subsequent sonar ping packets.
    """
    buf = bytearray()

    # 1. Base File Header (256 bytes)
    # '<bb8s8s16sh64s64s3hbbhbbHf12s10sl12f'
    base_hdr = struct.pack(
        XTF_FILE_HDR_BASE_FMT,
        XTF_MAGIC_BYTE,           # FileFormat (0x7B)
        1,                        # SystemType
        b"TESTPROG",              # RecordingProgramName
        b"1.00",                  # RecordingProgramVersion
        b"SYNTH_SSS",             # SonarName
        1,                        # SonarType
        b"Synthetic Test Note",   # NoteString
        b"test_synthetic.xtf",    # ThisFileName
        nav_units,                # NavUnits (1 = deg, 0 = meters)
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

    # 2. Six Channel Info Records (6 * 128 = 768 bytes)
    # '<bb3hl16s11fhb53s'
    for ch_idx in range(6):
        ch_type = 1 if ch_idx == 0 else (2 if ch_idx == 1 else 0)
        ch_name = b"Port" if ch_idx == 0 else (b"Starboard" if ch_idx == 1 else b"Unused")
        chan_hdr = struct.pack(
            XTF_CHAN_INFO_FMT,
            ch_type,              # TypeOfChannel (1=port, 2=stbd)
            ch_idx,               # SubChannelNumber
            0,                    # CorrectionFlags
            1,                    # UniPolar (1 = unsigned)
            1,                    # BytesPerSample (1 = uint8)
            1024,                 # Reserved
            ch_name.ljust(16, b"\x00"),
            1.0,                  # VoltScale
            455000.0 if ch_idx < 2 else 0.0,  # Frequency
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # 9 beam angles/offsets
            1,                    # BeamsPerArray
            8,                    # SampleFormat (8 = 1-byte int)
            b"\x00" * 53,         # ReservedArea2
        )
        buf.extend(chan_hdr)

    assert len(buf) == 1024, f"Header length must be 1024 bytes, got {len(buf)}"

    # 3. Sonar Ping Packets
    for p_idx in range(num_pings):
        p_samples = samples_per_chan + (p_idx * 10 if varying_lengths else 0)

        # 2 channels (Port + Starboard)
        # Each channel has 64-byte PingChanHeader + p_samples bytes
        chan_data_size = 2 * (64 + p_samples)
        total_pkt_bytes = 14 + 242 + chan_data_size

        # Packet Header (14 bytes)
        pkt_hdr = struct.pack(
            XTF_PACKET_HDR_FMT,
            XTF_PACKET_MAGIC,     # MagicNumber (0xFACE)
            XTF_HEADER_SONAR,     # HeaderType (0)
            0,                    # SubChannelNumber
            2,                    # NumChansToFollow (2)
            0, 0,                 # Reserved1, Reserved2
            total_pkt_bytes,      # NumBytesThisRecord
        )
        buf.extend(pkt_hdr)

        # Ping Header (242 bytes)
        eval_y = lat if lat is not None else 0.0
        eval_x = lon if lon is not None else 0.0
        eval_hdg = heading if heading is not None else 0.0
        eval_alt = altitude if altitude is not None else 0.0
        eval_depth = depth if depth is not None else 0.0

        ping_hdr = struct.pack(
            XTF_PING_HDR_FMT,
            2026, 9, 15,          # Year, Month, Day
            12, 0, p_idx, 0,      # Hour, Min, Sec, HSec
            258,                  # JulianDays
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
            p_samples, 1, 0.0, 0, 0, 0.0, 0, 0, 0, 0, 0
        )
        buf.extend(chan0_hdr)
        buf.extend(port_samples)

        # Channel 1: Starboard
        stbd_samples = np.full(p_samples, 80 + p_idx * 5, dtype=np.uint8).tobytes()
        chan1_hdr = struct.pack(
            XTF_PING_CHAN_HDR_FMT,
            1, 0, 50.0, 50.0, 0.0, 0.0, 0.1, 0, 455, 0, 0, 0, 0, 0, 0, 0,
            p_samples, 1, 0.0, 0, 0, 0.0, 0, 0, 0, 0, 0
        )
        buf.extend(chan1_hdr)
        buf.extend(stbd_samples)

    return bytes(buf)


class TestXtfSonarParserSynthetic(unittest.TestCase):
    """
    Unit tests for XtfSonarParser using specification-validated synthetic binary buffers.
    """

    @classmethod
    def setUpClass(cls):
        cls.parser = XtfSonarParser()

    # 1. Invalid / Non-XTF input
    def test_invalid_non_xtf_input(self):
        """Reject non-XTF formats like JPEG, empty buffers, and plain text."""
        self.assertFalse(self.parser.validate(b""))
        self.assertFalse(self.parser.validate(b"\xff\xd8\xff\xe0" + b"\x00" * 1024))
        self.assertFalse(self.parser.validate(b"RIFF\x00\x00\x00\x00WEBP"))

        with self.assertRaises(SonarFormatError):
            self.parser.parse_header(b"\x00" * 1024)

    # 2. Truncated / Corrupt file detection
    def test_truncated_corrupt_input(self):
        """Detect truncated headers and corrupt packet boundaries."""
        # Less than 1024 bytes
        with self.assertRaises(SonarCorruptFileError):
            self.parser.parse_header(b"\x7b" + b"\x00" * 500)

        # Valid header but packet with invalid byte length
        corrupt_buf = bytearray(build_synthetic_xtf_binary(num_pings=1))
        # Corrupt packet byte length field (index 1024 + 10 = NumBytesThisRecord)
        struct.pack_into("<I", corrupt_buf, 1024 + 10, 5)  # Less than 14 bytes
        with self.assertRaises(SonarCorruptFileError):
            self.parser.parse_pings(bytes(corrupt_buf))

    # 3. BaseSonarParser contract compliance
    def test_parser_contract_compliance(self):
        """Verify that XtfSonarParser strictly adheres to the BaseSonarParser interface."""
        self.assertIsInstance(self.parser, BaseSonarParser)
        valid_xtf = build_synthetic_xtf_binary(num_pings=2)
        self.assertTrue(self.parser.validate(valid_xtf))

        meta = self.parser.parse_header(valid_xtf)
        self.assertEqual(meta.format, SonarFormat.XTF)
        self.assertEqual(meta.total_pings, 2)
        self.assertEqual(len(meta.channels), 2)

        pings = self.parser.parse_pings(valid_xtf)
        self.assertEqual(len(pings), 2)

        nav = self.parser.extract_telemetry(valid_xtf)
        self.assertIsNotNone(nav)

        raster, spatial = self.parser.build_waterfall_raster(valid_xtf)
        self.assertEqual(raster.shape[0], 2)
        self.assertIn("nadir_pixel_x", spatial)

    # 4. Missing navigation fields preservation (None)
    def test_missing_navigation_fields(self):
        """When navigation fields are zero/unlogged, strictly output None."""
        xtf_no_nav = build_synthetic_xtf_binary(
            num_pings=2,
            lat=None,
            lon=None,
            heading=None,
            altitude=None,
            depth=None,
        )
        pings = self.parser.parse_pings(xtf_no_nav)
        self.assertEqual(len(pings), 2)
        for ping in pings:
            self.assertIsNone(ping.latitude)
            self.assertIsNone(ping.longitude)
            self.assertIsNone(ping.heading_deg)
            self.assertIsNone(ping.altitude_m)
            self.assertIsNone(ping.depth_m)

        nav = self.parser.extract_telemetry(xtf_no_nav)
        self.assertIsNone(nav)

    # 5. Sentinel coordinate / value handling
    def test_sentinel_handling(self):
        """Sentinels like (0.0, 0.0), -999.0, or projected meters must not be treated as valid WGS84."""
        # 1. Null Island (0.0, 0.0) sentinel
        xtf_zero_coords = build_synthetic_xtf_binary(num_pings=1, lat=0.0, lon=0.0)
        pings = self.parser.parse_pings(xtf_zero_coords)
        self.assertIsNone(pings[0].latitude)
        self.assertIsNone(pings[0].longitude)

        # 2. Sentinels (-999.0)
        xtf_sentinels = build_synthetic_xtf_binary(
            num_pings=1, lat=-999.0, lon=-999.0, heading=-999.0, altitude=-999.0, depth=-999.0
        )
        pings = self.parser.parse_pings(xtf_sentinels)
        self.assertIsNone(pings[0].latitude)
        self.assertIsNone(pings[0].longitude)
        self.assertIsNone(pings[0].heading_deg)
        self.assertIsNone(pings[0].altitude_m)
        self.assertIsNone(pings[0].depth_m)

        # 3. NavUnits == 0 (projected meters)
        xtf_projected = build_synthetic_xtf_binary(
            num_pings=1, nav_units=0, lat=350000.0, lon=4200000.0
        )
        meta = self.parser.parse_header(xtf_projected)
        self.assertTrue(any("NavUnits is set to 0" in w for w in meta.warnings))
        pings_proj = self.parser.parse_pings(xtf_projected)
        self.assertIsNone(pings_proj[0].latitude)
        self.assertIsNone(pings_proj[0].longitude)

    # 6. Bounded max_pings enforcement
    def test_bounded_max_pings(self):
        """Enforce strict memory bounds when max_pings is specified."""
        xtf_data = build_synthetic_xtf_binary(num_pings=8)

        pings_bounded = self.parser.parse_pings(xtf_data, max_pings=3)
        self.assertEqual(len(pings_bounded), 3)

        raster, _ = self.parser.build_waterfall_raster(xtf_data, max_pings=4)
        self.assertEqual(raster.shape[0], 4)

    # 7. Channel selection (Port, Starboard)
    def test_channel_selection(self):
        """Support selective rendering of Port (ch 0) or Starboard (ch 1)."""
        xtf_data = build_synthetic_xtf_binary(num_pings=2, samples_per_chan=50)

        # Port only
        raster_port, _ = self.parser.build_waterfall_raster(xtf_data, channels=[0])
        self.assertEqual(raster_port.shape[1], 50)

        # Starboard only
        raster_stbd, _ = self.parser.build_waterfall_raster(xtf_data, channels=[1])
        self.assertEqual(raster_stbd.shape[1], 50)

        # Both channels (Port + Starboard)
        raster_both, _ = self.parser.build_waterfall_raster(xtf_data, channels=[0, 1])
        self.assertEqual(raster_both.shape[1], 100)

    # 8. Varying sample length alignment
    def test_varying_sample_lengths(self):
        """Safely align pings with different sample counts into a uniform matrix."""
        xtf_varying = build_synthetic_xtf_binary(
            num_pings=3, samples_per_chan=40, varying_lengths=True
        )
        # Ping 0: 40 samples/chan, Ping 1: 50 samples/chan, Ping 2: 60 samples/chan
        # Max width for both channels = 2 * 60 = 120
        raster, spatial = self.parser.build_waterfall_raster(xtf_varying)
        self.assertEqual(raster.shape[0], 3)
        self.assertEqual(raster.shape[1], 120)
        self.assertEqual(spatial["sample_width"], 120)

    # 9. Waterfall raster generation and normalization
    def test_waterfall_raster_generation(self):
        """Confirm that generated raster is a valid 2D uint8 NumPy matrix within [0, 255]."""
        xtf_data = build_synthetic_xtf_binary(num_pings=4, samples_per_chan=60)
        raster, spatial = self.parser.build_waterfall_raster(xtf_data)

        self.assertIsInstance(raster, np.ndarray)
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(raster.shape, (4, 120))  # 4 pings, 60*2 width
        self.assertEqual(spatial["nadir_pixel_x"], 60.0)
        self.assertEqual(spatial["total_pings"], 4)
        self.assertEqual(spatial["format"], "XTF")
        self.assertGreaterEqual(int(np.min(raster)), 0)
        self.assertLessEqual(int(np.max(raster)), 255)

    # 10. Verification that GPS is never fabricated
    def test_no_fabricated_gps_values(self):
        """Under no circumstances should the parser fabricate default Karachi or Null Island GPS."""
        xtf_no_gps = build_synthetic_xtf_binary(num_pings=1, lat=None, lon=None)
        pings = self.parser.parse_pings(xtf_no_gps)
        self.assertIsNone(pings[0].latitude)
        self.assertIsNone(pings[0].longitude)
        self.assertFalse(pings[0].latitude == 24.8607)
        self.assertFalse(pings[0].longitude == 67.0011)


class TestXtfRealFileIntegration(unittest.TestCase):
    """
    Integration test suite for real-world XTF sonar recordings.
    Execution is conditionally skipped until a physical sample file is added.
    """

    REAL_XTF_CANDIDATE_PATHS: List[str] = [
        "data/sample.xtf",
        "tests/data/sample.xtf",
        "sample_sidescan.xtf",
    ]

    def test_real_xtf_fixture_validation(self):
        real_file = next((p for p in self.REAL_XTF_CANDIDATE_PATHS if os.path.exists(p)), None)
        if real_file is None:
            self.skipTest(
                "Real .xtf fixture not available in repository; real-file integration testing remains pending."
            )

        parser = XtfSonarParser()
        self.assertTrue(parser.validate(real_file))
        meta = parser.parse_header(real_file)
        self.assertEqual(meta.format, SonarFormat.XTF)
        self.assertGreater(meta.file_size_bytes, 1024)


if __name__ == "__main__":
    unittest.main()
