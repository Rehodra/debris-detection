"""
Extended Triton Format (XTF) Raw Sonar Ingestion and Parsing Engine.
Implements XtfSonarParser fulfilling the BaseSonarParser interface for .xtf files.

Specification references:
  - Triton Imaging Inc. eXtended Triton Format (XTF) Rev 35 / Rev 42
  - pyxtf reference byte structures and ctypes layouts
"""

import io
import math
import struct
from pathlib import Path
from typing import BinaryIO, Dict, Any, List, Optional, Tuple, Union

import numpy as np

from app.schemas.sonar import (
    SonarChannelInfo,
    SonarFileMetadata,
    SonarFormat,
    SonarNavigation,
    SonarPingTelemetry,
)
from app.sonar.base import (
    BaseSonarParser,
    SonarCorruptFileError,
    SonarFormatError,
    open_binary_source,
)
from app.sonar.raster_reader import SonarRasterBuilder

# =============================================================================
# XTF Binary Struct Formats (Little-Endian '<')
# =============================================================================

# Magic byte identifying Triton XTF file format
XTF_MAGIC_BYTE = 0x7B  # 123 decimal

# Magic number identifying start of XTF packet
XTF_PACKET_MAGIC = 0xFACE  # 64206 unsigned, -1330 signed int16

# Packet header types
XTF_HEADER_SONAR = 0       # Sidescan sonar ping packet
XTF_HEADER_ANNOTATION = 1  # Notes / annotation packet
XTF_HEADER_ATTITUDE = 3    # Attitude / gyro packet
XTF_HEADER_POSITION = 2    # Position packet
XTF_HEADER_BATHYMETRY = 4  # Bathymetry packet

# Base file header structure (256 bytes):
# FileFormat(b), SystemType(b), RecordingProgramName(8s), RecordingProgramVersion(8s),
# SonarName(16s), SonarType(h), NoteString(64s), ThisFileName(64s), NavUnits(h),
# NumberOfSonarChannels(h), NumberOfBathymetryChannels(h), NumberOfSnippetChannels(b),
# NumberOfForwardLookArrays(b), NumberOfEchoStrengthChannels(h), NumberOfInterferometryChannels(b),
# Reserved1(b), Reserved2(h), ReferencePointHeight(f), ProjectionType(12s),
# SpheroidType(10s), NavigationLatency(l), OriginX(f), OriginY(f), 10 Nav/MRU offsets (10f)
XTF_FILE_HDR_BASE_FMT = "<bb8s8s16sh64s64s3hbbhbbHf12s10sl12f"
XTF_FILE_HDR_BASE_LEN = struct.calcsize(XTF_FILE_HDR_BASE_FMT)  # 256 bytes

# Channel info structure (128 bytes each, 6 per 1024-byte header block):
# TypeOfChannel(b), SubChannelNumber(b), CorrectionFlags(h), UniPolar(h),
# BytesPerSample(h), Reserved(l), ChannelName(16s), VoltScale(f), Frequency(f),
# HorizBeamAngle(f), TiltAngle(f), BeamWidth(f), OffsetX(f), OffsetY(f), OffsetZ(f),
# OffsetYaw(f), OffsetPitch(f), OffsetRoll(f), BeamsPerArray(h), SampleFormat(b), ReservedArea2(53s)
XTF_CHAN_INFO_FMT = "<bb3hl16s11fhb53s"
XTF_CHAN_INFO_LEN = struct.calcsize(XTF_CHAN_INFO_FMT)  # 128 bytes

# Packet header structure (14 bytes):
# MagicNumber(h), HeaderType(b), SubChannelNumber(b), NumChansToFollow(h),
# Reserved1(h), Reserved2(h), NumBytesThisRecord(I)
XTF_PACKET_HDR_FMT = "<H2b3hI"
XTF_PACKET_HDR_LEN = struct.calcsize(XTF_PACKET_HDR_FMT)  # 14 bytes

# Ping header structure (242 bytes, follows the 14-byte packet header to total 256 bytes):
# Year(h), Month(b), Day(b), Hour(b), Minute(b), Second(b), HSeconds(b), JulianDays(h),
# EventNumber(I), PingNumber(I), SoundVelocity(f), OceanTide(f), Reserved2(I),
# 21 sensory floats (21f), ShipYcoordinate(d), ShipXcoordinate(d), ShipAltitude(h), ShipDepth(h),
# FixTime(4b), SensorSpeed(f), KP(f), SensorYcoordinate(d), SensorXcoordinate(d),
# SonarStatus(h), RangeToTowFish(h), BearingToTowFish(h), CableOut(h),
# 10 attitude/sensor floats (10f: Layback, Tension, SensorDepth, SensorPrimaryAltitude, AuxAlt, Pitch, Roll, Heading, Heave, Yaw),
# AttitudeTimeTag(I), DOT(f), NavFixMilliseconds(I), ComputerClock(4b),
# FishPositionDeltaX(h), FishPositionDeltaY(h), FishPositionErrorCode(B), OptionalOffset(I), ReservedSpace(7s)
XTF_PING_HDR_FMT = "<h6bh2I2fI21f2d2h4b2f2d4h10fIfI4b2hBI7s"
XTF_PING_HDR_LEN = struct.calcsize(XTF_PING_HDR_FMT)  # 242 bytes

# Ping Channel Header structure (64 bytes per channel):
# ChannelNumber(h), DownsampleMethod(h), SlantRange(f), GroundRange(f), TimeDelay(f),
# TimeDuration(f), SecondsPerPing(f), ProcessingFlags(h), Frequency(h), InitialGainCode(h),
# GainCode(h), BandWidth(h), ContactNumber(I), ContactClassification(h), ContactSubNumber(b),
# ContactType(b), NumSamples(I), MillivoltScale(h), ContactTimeOffTrack(f), ContactCloseNumber(b),
# Reserved2(b), FixedVSOP(f), Weight(h), ReservedSpace(4b)
XTF_PING_CHAN_HDR_FMT = "<2h5f5hIh2bIhf2bfh4b"
XTF_PING_CHAN_HDR_LEN = struct.calcsize(XTF_PING_CHAN_HDR_FMT)  # 64 bytes


class XtfSonarParser(BaseSonarParser):
    """
    Production-grade parser for Extended Triton Format (.xtf) sidescan sonar files.
    Extracts file structure, channel layouts, per-ping navigation & acoustic samples,
    and constructs normalized waterfall matrices.
    """

    def validate(self, source: Union[str, Path, BinaryIO, bytes]) -> bool:
        """Verify whether source contains a valid Triton XTF header signature."""
        try:
            with open_binary_source(source) as stream:
                stream.seek(0)
                first_byte = stream.read(1)
                if not first_byte or first_byte[0] != XTF_MAGIC_BYTE:
                    return False

                # Ensure minimum file header size (1024 bytes)
                stream.seek(0, io.SEEK_END)
                file_size = stream.tell()
                if file_size < 1024:
                    return False

                # Check if first packet has valid magic (0xFACE) if data exists beyond header
                if file_size >= 1024 + XTF_PACKET_HDR_LEN:
                    stream.seek(1024)
                    pkt_bytes = stream.read(XTF_PACKET_HDR_LEN)
                    if len(pkt_bytes) == XTF_PACKET_HDR_LEN:
                        magic, _, _, _, _, _, _ = struct.unpack(XTF_PACKET_HDR_FMT, pkt_bytes)
                        # 0xFACE can unpack as unsigned 64206 or signed -1330
                        if (magic & 0xFFFF) != XTF_PACKET_MAGIC:
                            return False

                return True
        except Exception:
            return False

    def parse_header(self, source: Union[str, Path, BinaryIO, bytes]) -> SonarFileMetadata:
        """
        Parse 1024-byte file header and channel descriptors.
        Strictly preserves missing information without fabricating values.
        """
        filename = "unknown.xtf"
        if isinstance(source, (str, Path)):
            filename = Path(source).name

        warnings: List[str] = []

        with open_binary_source(source) as stream:
            stream.seek(0, io.SEEK_END)
            file_size = stream.tell()
            if file_size < 1024:
                raise SonarCorruptFileError(f"File size ({file_size} bytes) is smaller than minimum XTF header (1024 bytes).")

            stream.seek(0)
            base_bytes = stream.read(XTF_FILE_HDR_BASE_LEN)
            if len(base_bytes) < XTF_FILE_HDR_BASE_LEN:
                raise SonarCorruptFileError("Premature EOF while reading XTF base file header.")

            unpacked_base = struct.unpack(XTF_FILE_HDR_BASE_FMT, base_bytes)
            file_format = unpacked_base[0]
            if file_format != XTF_MAGIC_BYTE:
                raise SonarFormatError(f"Invalid XTF magic byte: 0x{file_format:02X} (expected 0x7B).")

            # Extract fields
            recording_program = unpacked_base[2].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            recording_version = unpacked_base[3].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            sonar_name = unpacked_base[4].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            header_file_name = unpacked_base[7].decode("utf-8", errors="ignore").rstrip("\x00").strip()
            if header_file_name and filename == "unknown.xtf":
                filename = header_file_name

            nav_units = unpacked_base[8]
            if nav_units == 0:
                warnings.append("XTF NavUnits is set to 0 (grid/projected meters). Geodetic Lat/Lon is unavailable.")
            elif nav_units not in (1, 2):
                warnings.append(f"XTF NavUnits is set to unknown code {nav_units}.")

            num_sonar_channels = max(0, unpacked_base[9])
            num_bathy_channels = max(0, unpacked_base[10])
            total_declared_channels = num_sonar_channels + num_bathy_channels

            # Read 6 channel descriptors
            channels: List[SonarChannelInfo] = []
            for ch_idx in range(6):
                chan_bytes = stream.read(XTF_CHAN_INFO_LEN)
                if len(chan_bytes) < XTF_CHAN_INFO_LEN:
                    raise SonarCorruptFileError(f"Premature EOF while reading ChanInfo[{ch_idx}].")

                u_chan = struct.unpack(XTF_CHAN_INFO_FMT, chan_bytes)
                chan_type = u_chan[0]
                bytes_per_sample = u_chan[4]
                raw_name = u_chan[6].decode("utf-8", errors="ignore").rstrip("\x00").strip()
                volt_scale = u_chan[7]
                freq = u_chan[8] if u_chan[8] > 0 else None
                sample_format_code = u_chan[19]

                # Map channel name and type
                if not raw_name:
                    if chan_type == 1:
                        raw_name = "port"
                    elif chan_type == 2:
                        raw_name = "starboard"
                    elif chan_type == 0:
                        raw_name = "subbottom"
                    else:
                        raw_name = f"channel_{ch_idx}"

                sample_fmt_str = "uint8" if bytes_per_sample == 1 else "uint16"
                if sample_format_code == 5:
                    sample_fmt_str = "float32"

                is_active = (ch_idx < total_declared_channels) or (chan_type in (1, 2) and freq is not None)

                if is_active or ch_idx < max(2, num_sonar_channels):
                    channels.append(
                        SonarChannelInfo(
                            channel_id=ch_idx,
                            channel_name=raw_name.lower(),
                            frequency_hz=freq,
                            sample_count=None,
                            range_m=None,
                            sample_format=sample_fmt_str,
                            available=is_active,
                        )
                    )

            # Count total pings and check navigation availability by scanning packet headers
            stream.seek(1024)
            total_pings = 0
            has_nav = False

            while True:
                pkt_pos = stream.tell()
                pkt_bytes = stream.read(XTF_PACKET_HDR_LEN)
                if len(pkt_bytes) < XTF_PACKET_HDR_LEN:
                    break

                magic, hdr_type, _, num_chans, _, _, num_bytes = struct.unpack(XTF_PACKET_HDR_FMT, pkt_bytes)
                if (magic & 0xFFFF) != XTF_PACKET_MAGIC:
                    break
                if num_bytes < XTF_PACKET_HDR_LEN:
                    raise SonarCorruptFileError(f"Corrupt packet at byte {pkt_pos}: declared size ({num_bytes}) is invalid.")

                if hdr_type == XTF_HEADER_SONAR:
                    total_pings += 1
                    # Inspect navigation in the first few pings if not yet confirmed
                    if not has_nav and total_pings <= 10 and (num_bytes >= XTF_PACKET_HDR_LEN + XTF_PING_HDR_LEN):
                        ping_bytes = stream.read(XTF_PING_HDR_LEN)
                        if len(ping_bytes) == XTF_PING_HDR_LEN:
                            u_ping = struct.unpack(XTF_PING_HDR_FMT, ping_bytes)
                            nav_fix = self._extract_nav_from_ping_tuple(u_ping, nav_units)
                            if nav_fix and nav_fix.latitude is not None and nav_fix.longitude is not None:
                                has_nav = True
                        stream.seek(pkt_pos + num_bytes)
                        continue

                # Seek to next packet
                stream.seek(pkt_pos + num_bytes)

            return SonarFileMetadata(
                filename=filename,
                format=SonarFormat.XTF,
                file_size_bytes=file_size,
                total_pings=total_pings,
                channel_count=len(channels),
                channels=channels,
                navigation_available=has_nav,
                warnings=warnings,
            )

    def parse_pings(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
    ) -> List[SonarPingTelemetry]:
        """
        Parse sequential acoustic ping records and extract per-ping navigation/sensor telemetry.
        Never fabricates GPS coordinates or altitude/depth. Missing fields strictly remain None.
        """
        pings: List[SonarPingTelemetry] = []

        with open_binary_source(source) as stream:
            # Read NavUnits from file header
            stream.seek(0)
            base_bytes = stream.read(XTF_FILE_HDR_BASE_LEN)
            if len(base_bytes) < XTF_FILE_HDR_BASE_LEN:
                raise SonarCorruptFileError("Premature EOF while reading XTF file header.")

            unpacked_base = struct.unpack(XTF_FILE_HDR_BASE_FMT, base_bytes)
            if unpacked_base[0] != XTF_MAGIC_BYTE:
                raise SonarFormatError("Not a valid XTF file.")
            nav_units = unpacked_base[8]

            # Seek to first packet offset
            stream.seek(1024)
            ping_idx = 0

            while True:
                if max_pings is not None and ping_idx >= max_pings:
                    break

                pkt_pos = stream.tell()
                pkt_bytes = stream.read(XTF_PACKET_HDR_LEN)
                if len(pkt_bytes) < XTF_PACKET_HDR_LEN:
                    break

                magic, hdr_type, _, _, _, _, num_bytes = struct.unpack(XTF_PACKET_HDR_FMT, pkt_bytes)
                if (magic & 0xFFFF) != XTF_PACKET_MAGIC:
                    # Trailing padding or EOF reached
                    break
                if num_bytes < XTF_PACKET_HDR_LEN:
                    raise SonarCorruptFileError(f"Corrupt packet at byte {pkt_pos}: declared size ({num_bytes}) is invalid.")

                if hdr_type == XTF_HEADER_SONAR:
                    if num_bytes < XTF_PACKET_HDR_LEN + XTF_PING_HDR_LEN:
                        raise SonarCorruptFileError(f"Sonar packet at byte {pkt_pos} has invalid length {num_bytes}.")

                    ping_bytes = stream.read(XTF_PING_HDR_LEN)
                    if len(ping_bytes) < XTF_PING_HDR_LEN:
                        raise SonarCorruptFileError(f"Truncated ping header at byte {pkt_pos}.")

                    u_ping = struct.unpack(XTF_PING_HDR_FMT, ping_bytes)
                    nav = self._extract_nav_from_ping_tuple(u_ping, nav_units)

                    timestamp_str = None
                    year, month, day, hour, minute, second, hsecond = u_ping[0], u_ping[1], u_ping[2], u_ping[3], u_ping[4], u_ping[5], u_ping[6]
                    if year >= 1970 and 1 <= month <= 12 and 1 <= day <= 31:
                        timestamp_str = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}.{hsecond * 10:03d}Z"

                    pings.append(
                        SonarPingTelemetry(
                            ping_index=ping_idx,
                            timestamp=timestamp_str,
                            latitude=nav.latitude if nav else None,
                            longitude=nav.longitude if nav else None,
                            heading_deg=nav.heading_deg if nav else None,
                            altitude_m=nav.altitude_m if nav else None,
                            depth_m=nav.depth_m if nav else None,
                        )
                    )
                    ping_idx += 1

                # Advance to next packet
                stream.seek(pkt_pos + num_bytes)

        return pings

    def extract_telemetry(self, source: Union[str, Path, BinaryIO, bytes]) -> Optional[SonarNavigation]:
        """
        Extract the primary or representative survey navigation fix from the file.
        Returns None if no valid GPS fix is present.
        """
        pings = self.parse_pings(source, max_pings=50)
        for ping in pings:
            if ping.latitude is not None and ping.longitude is not None:
                return SonarNavigation(
                    timestamp=ping.timestamp,
                    latitude=ping.latitude,
                    longitude=ping.longitude,
                    heading_deg=ping.heading_deg,
                    altitude_m=ping.altitude_m,
                    depth_m=ping.depth_m,
                    source="xtf_ping_header",
                )

        return None

    def build_waterfall_raster(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Assemble raw acoustic ping channels into a normalized 2D NumPy waterfall matrix.
        Rows represent sequential pings; columns represent acoustic range/sample bins.

        Layout:
          - If Port & Starboard are present: Port is flipped horizontally (nadir in center),
            followed by Starboard, so nadir ground track runs down the middle.
          - If single channel is requested, yields that channel's direct samples.
          - Normalizes dynamic range safely to uint8 (0..255) using robust percentile scaling.
        """
        pings_channels: List[Dict[int, np.ndarray]] = []
        slant_ranges: List[Optional[float]] = []

        with open_binary_source(source) as stream:
            # Inspect file header for channel byte sizes
            stream.seek(0)
            base_bytes = stream.read(XTF_FILE_HDR_BASE_LEN)
            if len(base_bytes) < XTF_FILE_HDR_BASE_LEN:
                raise SonarCorruptFileError("Cannot build raster: header truncated.")

            unpacked_base = struct.unpack(XTF_FILE_HDR_BASE_FMT, base_bytes)
            if unpacked_base[0] != XTF_MAGIC_BYTE:
                raise SonarFormatError("Not a valid XTF file.")

            # Read channel info to know BytesPerSample & UniPolar per channel
            chan_byte_specs: Dict[int, Tuple[int, int]] = {}
            for ch_idx in range(6):
                cb = stream.read(XTF_CHAN_INFO_LEN)
                if len(cb) == XTF_CHAN_INFO_LEN:
                    u_ch = struct.unpack(XTF_CHAN_INFO_FMT, cb)
                    unipolar = u_ch[3]
                    bytes_per_sample = u_ch[4] if u_ch[4] in (1, 2) else 1
                    chan_byte_specs[ch_idx] = (bytes_per_sample, unipolar)

            stream.seek(1024)
            pings_read = 0

            while True:
                if max_pings is not None and pings_read >= max_pings:
                    break

                pkt_pos = stream.tell()
                pkt_bytes = stream.read(XTF_PACKET_HDR_LEN)
                if len(pkt_bytes) < XTF_PACKET_HDR_LEN:
                    break

                magic, hdr_type, _, num_chans, _, _, num_bytes = struct.unpack(XTF_PACKET_HDR_FMT, pkt_bytes)
                if (magic & 0xFFFF) != XTF_PACKET_MAGIC:
                    break
                if num_bytes < XTF_PACKET_HDR_LEN:
                    raise SonarCorruptFileError(f"Corrupt packet at byte {pkt_pos}: declared size ({num_bytes}) is invalid.")

                if hdr_type == XTF_HEADER_SONAR:
                    stream.seek(pkt_pos + XTF_PACKET_HDR_LEN + XTF_PING_HDR_LEN)

                    channel_arrays: Dict[int, np.ndarray] = {}
                    ping_slant_range: Optional[float] = None

                    # Read channel data records
                    for ch_idx in range(num_chans):
                        chan_hdr_bytes = stream.read(XTF_PING_CHAN_HDR_LEN)
                        if len(chan_hdr_bytes) < XTF_PING_CHAN_HDR_LEN:
                            break

                        u_chan_hdr = struct.unpack(XTF_PING_CHAN_HDR_FMT, chan_hdr_bytes)
                        ch_num = u_chan_hdr[0]
                        slant_range = u_chan_hdr[2]
                        num_samples = u_chan_hdr[16]

                        if slant_range > 0 and ping_slant_range is None:
                            ping_slant_range = slant_range

                        bps, unipolar = chan_byte_specs.get(ch_num, (1, 1))
                        sample_bytes_len = num_samples * bps
                        raw_sample_bytes = stream.read(sample_bytes_len)

                        if len(raw_sample_bytes) == sample_bytes_len and num_samples > 0:
                            dtype = np.uint8 if bps == 1 else np.uint16
                            samples = np.frombuffer(raw_sample_bytes, dtype=dtype)
                            channel_arrays[ch_num] = samples

                    pings_channels.append(channel_arrays)
                    slant_ranges.append(ping_slant_range)
                    pings_read += 1

                # Seek to exact start of next packet
                stream.seek(pkt_pos + num_bytes)

        raster, spatial_metadata = SonarRasterBuilder.assemble_scanlines(
            pings_channels=pings_channels,
            requested_channels=channels,
            slant_ranges=slant_ranges,
            max_pings=max_pings,
        )
        spatial_metadata["format"] = "XTF"
        return raster, spatial_metadata

    # -------------------------------------------------------------------------
    # Helper: Navigation & Sentinel Validation
    # -------------------------------------------------------------------------

    def _extract_nav_from_ping_tuple(
        self,
        u_ping: tuple,
        nav_units: int,
    ) -> Optional[SonarNavigation]:
        """
        Extract coordinates, heading, altitude, and depth from unpacked ping header.
        Applies rigorous sentinel filtering:
          - (0.0, 0.0) is treated as missing GPS.
          - Negative/sentinel altitude/depth/heading are treated as missing (None).
          - NavUnits == 0 (grid/meters) is never converted to latitude/longitude.
        """
        # Sensor coordinates (double float64)
        sensor_y = u_ping[44]  # SensorY
        sensor_x = u_ping[45]  # SensorX

        # Ship coordinates (double float64)
        ship_y = u_ping[34]    # ShipY
        ship_x = u_ping[35]    # ShipX

        lat: Optional[float] = None
        lon: Optional[float] = None

        # Only interpret as geodetic degrees if NavUnits == 1 (degrees)
        if nav_units == 1:
            # Prefer sensor coordinates; fall back to ship coordinates
            coords_to_eval = (sensor_y, sensor_x)
            if self._is_sentinel_coordinate(sensor_y, sensor_x):
                coords_to_eval = (ship_y, ship_x)

            eval_lat, eval_lon = coords_to_eval
            if not self._is_sentinel_coordinate(eval_lat, eval_lon):
                if -90.0 <= eval_lat <= 90.0 and -180.0 <= eval_lon <= 180.0:
                    lat = round(eval_lat, 7)
                    lon = round(eval_lon, 7)

        # Heading: check SensorHeading (index 57) then ShipGyro (index 33)
        heading_deg: Optional[float] = None
        sensor_hdg = u_ping[57]
        ship_gyro = u_ping[33]

        eval_hdg = sensor_hdg if not self._is_sentinel_float(sensor_hdg) else ship_gyro
        if not self._is_sentinel_float(eval_hdg):
            if 0.0 <= eval_hdg <= 360.0:
                heading_deg = round(eval_hdg, 2)

        # Altitude: SensorPrimaryAltitude (index 53)
        altitude_m: Optional[float] = None
        sensor_alt = u_ping[53]
        if not self._is_sentinel_float(sensor_alt) and 0.1 <= sensor_alt <= 10000.0:
            altitude_m = round(sensor_alt, 3)

        # Depth: SensorDepth (index 52) then ShipDepth (index 37)
        depth_m: Optional[float] = None
        sensor_depth = u_ping[52]
        if not self._is_sentinel_float(sensor_depth) and 0.0 <= sensor_depth <= 12000.0:
            depth_m = round(sensor_depth, 3)
        elif u_ping[37] > 0 and not self._is_sentinel_float(float(u_ping[37])):
            depth_m = round(float(u_ping[37]), 3)

        return SonarNavigation(
            latitude=lat,
            longitude=lon,
            heading_deg=heading_deg,
            altitude_m=altitude_m,
            depth_m=depth_m,
            source="xtf_ping_header",
        )

    @staticmethod
    def _is_sentinel_coordinate(lat: float, lon: float) -> bool:
        """Check if coordinates represent uncalibrated sentinels or Null Island (0.0, 0.0)."""
        if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
            return True
        # Exact 0.0, 0.0 or near-zero unpopulated values
        if abs(lat) < 1e-6 and abs(lon) < 1e-6:
            return True
        # Common sentinel fill values (-999.0, -1.0, 0x7FFFFFFF)
        if lat in (-999.0, -9999.0, -1.0) or lon in (-999.0, -9999.0, -1.0):
            return True
        return False

    @staticmethod
    def _is_sentinel_float(val: float) -> bool:
        """Check if floating point sensor telemetry represents an uncalibrated sentinel."""
        if math.isnan(val) or math.isinf(val):
            return True
        if val in (-999.0, -9999.0, -1.0, 9999.0, 0.0):
            return True
        return False
