"""
Unit tests for MarineScan Sonar Schemas and Base Parser Interface.
Validates Pydantic v2 models, strict None-handling for missing metadata,
and the abstract BaseSonarParser contract.
"""

import io
import tempfile
import unittest
from pathlib import Path
from typing import BinaryIO, Dict, Any, List, Optional, Tuple, Union

import numpy as np
from pydantic import ValidationError

from app.schemas.sonar import (
    SonarChannelInfo,
    SonarFileMetadata,
    SonarFormat,
    SonarNavigation,
    SonarParseResult,
    SonarPingTelemetry,
)
from app.sonar.base import (
    BaseSonarParser,
    SonarCorruptFileError,
    SonarFormatError,
    SonarNavigationError,
    SonarParserError,
    open_binary_source,
)


class DummySonarParser(BaseSonarParser):
    """Minimal concrete parser implementation for testing the abstract interface."""

    def validate(self, source: Union[str, Path, BinaryIO, bytes]) -> bool:
        with open_binary_source(source) as stream:
            header = stream.read(4)
            return header == b"\x7b\x01\x00\x00"

    def parse_header(self, source: Union[str, Path, BinaryIO, bytes]) -> SonarFileMetadata:
        with open_binary_source(source) as stream:
            data = stream.read()
            if len(data) < 4:
                raise SonarCorruptFileError("Header too short")
            if not self.validate(data):
                raise SonarFormatError("Invalid magic header")
            return SonarFileMetadata(
                filename="dummy.xtf",
                format="XTF",
                file_size_bytes=len(data),
                total_pings=1,
                channel_count=2,
                channels=[
                    SonarChannelInfo(channel_id=0, channel_name="port", frequency_hz=100000.0),
                    SonarChannelInfo(channel_id=1, channel_name="starboard", frequency_hz=100000.0),
                ],
                navigation_available=False,
                warnings=[],
            )

    def parse_pings(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
    ) -> List[SonarPingTelemetry]:
        return [
            SonarPingTelemetry(
                ping_index=0,
                timestamp="2026-09-15T00:00:00Z",
                latitude=None,
                longitude=None,
                heading_deg=None,
                altitude_m=None,
                depth_m=None,
            )
        ]

    def extract_telemetry(self, source: Union[str, Path, BinaryIO, bytes]) -> Optional[SonarNavigation]:
        return None

    def build_waterfall_raster(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        raster = np.zeros((1, 100), dtype=np.uint8)
        return raster, {"nadir_pixel_x": 50, "meters_per_pixel": 0.05}


class TestSonarSchemas(unittest.TestCase):
    """Test suite for Sonar Pydantic v2 schemas and strict None preservation."""

    def test_sonar_navigation_all_none(self):
        """Verify that optional navigation fields default to None without fabrication."""
        nav = SonarNavigation()
        self.assertIsNone(nav.timestamp)
        self.assertIsNone(nav.latitude)
        self.assertIsNone(nav.longitude)
        self.assertIsNone(nav.heading_deg)
        self.assertIsNone(nav.altitude_m)
        self.assertIsNone(nav.depth_m)
        self.assertIsNone(nav.source)

    def test_sonar_navigation_populated(self):
        """Verify populated navigation fix preserves valid coordinate ranges."""
        nav = SonarNavigation(
            timestamp="2026-09-15T00:00:00Z",
            latitude=24.8607,
            longitude=67.0011,
            heading_deg=185.5,
            altitude_m=12.4,
            depth_m=18.6,
            source="primary_nav",
        )
        self.assertEqual(nav.latitude, 24.8607)
        self.assertEqual(nav.longitude, 67.0011)
        self.assertEqual(nav.heading_deg, 185.5)
        self.assertEqual(nav.altitude_m, 12.4)
        self.assertEqual(nav.depth_m, 18.6)
        self.assertEqual(nav.source, "primary_nav")

    def test_sonar_navigation_invalid_coordinates(self):
        """Ensure coordinate bounds are strictly enforced by Pydantic."""
        with self.assertRaises(ValidationError):
            SonarNavigation(latitude=95.0)  # Outside [-90, 90]

        with self.assertRaises(ValidationError):
            SonarNavigation(longitude=-190.0)  # Outside [-180, 180]

        with self.assertRaises(ValidationError):
            SonarNavigation(heading_deg=370.0)  # Outside [0, 360]

    def test_sonar_channel_info_missing_parameters(self):
        """Channel metadata must allow None for optional acquisition parameters."""
        chan = SonarChannelInfo(channel_id=0, channel_name="port")
        self.assertEqual(chan.channel_id, 0)
        self.assertEqual(chan.channel_name, "port")
        self.assertIsNone(chan.frequency_hz)
        self.assertIsNone(chan.sample_count)
        self.assertIsNone(chan.range_m)
        self.assertIsNone(chan.sample_format)
        self.assertTrue(chan.available)

    def test_sonar_ping_telemetry_missing_nav(self):
        """Ping telemetry must not fabricate GPS or sensor altitude/depth."""
        ping = SonarPingTelemetry(ping_index=42)
        self.assertEqual(ping.ping_index, 42)
        self.assertIsNone(ping.timestamp)
        self.assertIsNone(ping.latitude)
        self.assertIsNone(ping.longitude)
        self.assertIsNone(ping.heading_deg)
        self.assertIsNone(ping.altitude_m)
        self.assertIsNone(ping.depth_m)

    def test_sonar_file_metadata_and_parse_result(self):
        """Test composite SonarParseResult model."""
        meta = SonarFileMetadata(
            filename="survey_line_01.xtf",
            format="XTF",
            file_size_bytes=1048576,
            total_pings=500,
            channel_count=2,
            channels=[
                SonarChannelInfo(channel_id=0, channel_name="port", frequency_hz=455000.0, range_m=50.0),
                SonarChannelInfo(channel_id=1, channel_name="starboard", frequency_hz=455000.0, range_m=50.0),
            ],
            navigation_available=True,
            warnings=["Dropped 1 corrupt attitude packet at ping 214"],
        )
        self.assertEqual(meta.format, SonarFormat.XTF)
        self.assertEqual(len(meta.channels), 2)
        self.assertTrue(meta.navigation_available)

        result = SonarParseResult(
            metadata=meta,
            navigation=SonarNavigation(latitude=24.86, longitude=67.00),
            pings=[],
            warnings=meta.warnings,
            errors=[],
        )
        self.assertEqual(result.metadata.filename, "survey_line_01.xtf")
        self.assertIsNotNone(result.navigation)
        self.assertEqual(len(result.warnings), 1)


class TestSonarBaseParser(unittest.TestCase):
    """Test suite for BaseSonarParser abstraction and open_binary_source utility."""

    def test_cannot_instantiate_abstract_parser(self):
        """BaseSonarParser must enforce abstract methods and reject direct instantiation."""
        with self.assertRaises(TypeError):
            BaseSonarParser()  # type: ignore

    def test_dummy_parser_validation_and_parsing(self):
        """Concrete parser must fulfill the BaseSonarParser contract."""
        valid_bytes = b"\x7b\x01\x00\x00\x00\x00\x00\x00"
        parser = DummySonarParser()

        # Test validation
        self.assertTrue(parser.validate(valid_bytes))
        self.assertFalse(parser.validate(b"\x00\x00\x00\x00"))

        # Test parse_header
        meta = parser.parse_header(valid_bytes)
        self.assertEqual(meta.format, "XTF")
        self.assertEqual(meta.channel_count, 2)

        # Test parse_pings
        pings = parser.parse_pings(valid_bytes)
        self.assertEqual(len(pings), 1)
        self.assertIsNone(pings[0].latitude)

        # Test extract_telemetry
        nav = parser.extract_telemetry(valid_bytes)
        self.assertIsNone(nav)

        # Test build_waterfall_raster
        raster, spatial = parser.build_waterfall_raster(valid_bytes)
        self.assertEqual(raster.shape, (1, 100))
        self.assertEqual(spatial["nadir_pixel_x"], 50)

        # Test high-level parse method
        res = parser.parse(valid_bytes)
        self.assertEqual(res.metadata.filename, "dummy.xtf")
        self.assertEqual(len(res.pings), 1)

    def test_open_binary_source_types(self):
        """Verify open_binary_source supports bytes, BytesIO, and filepath inputs."""
        payload = b"TEST_SONAR_PAYLOAD"

        # 1. Raw bytes
        with open_binary_source(payload) as f:
            self.assertEqual(f.read(), payload)

        # 2. BytesIO stream
        bio = io.BytesIO(payload)
        with open_binary_source(bio) as f:
            self.assertEqual(f.read(), payload)
        self.assertFalse(bio.closed)  # Pre-existing stream should not be closed

        # 3. Temp file path
        with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
            tf.write(payload)
            tf_path = Path(tf.name)

        try:
            with open_binary_source(tf_path) as f:
                self.assertEqual(f.read(), payload)
            with open_binary_source(str(tf_path)) as f:
                self.assertEqual(f.read(), payload)
        finally:
            tf_path.unlink(missing_ok=True)

        # 4. Invalid source type raises TypeError
        with self.assertRaises(TypeError):
            with open_binary_source(12345):  # type: ignore
                pass

    def test_sonar_exceptions_hierarchy(self):
        """Verify exception inheritance under SonarParserError."""
        self.assertTrue(issubclass(SonarFormatError, SonarParserError))
        self.assertTrue(issubclass(SonarCorruptFileError, SonarParserError))
        self.assertTrue(issubclass(SonarNavigationError, SonarParserError))


if __name__ == "__main__":
    unittest.main()
