"""
EdgeTech Just Sonar File (.jsf) Reader and Decoder for MarineScan.
Decodes EdgeTech sonar files into normalized telemetry, metadata, and waterfall matrices.

Format Specification (EdgeTech JSF File Format 990-0000048-1000 / 0023492):
  - Byte Order: Little-Endian (Intel) for all binary fields.
  - File Structure: Sequential stream of discrete messages.
  - Message Header (16 bytes, JSF_MSG_HDR_FMT = "<HBBHBBBBHI"):
      * Bytes 0–1   : Start-of-header marker = 0x1601 (UINT16)
      * Byte  2     : Protocol revision level (UINT8)
      * Byte  3     : Session identifier (UINT8)
      * Bytes 4–5   : Message Type (UINT16), e.g. 80 = Sonar Data
      * Byte  6     : Command type (UINT8)
      * Byte  7     : Subsystem number (UINT8, e.g. 20 for sidescan)
      * Byte  8     : Channel number (UINT8, 0 = Port, 1 = Starboard)
      * Byte  9     : Sequence number (UINT8)
      * Bytes 10–11 : Reserved (UINT16)
      * Bytes 12–15 : Byte count of message payload following this header (UINT32)

  - Message Type 80 (Sonar Data Message, payload = 240-byte trace header + samples):
      * Bytes 0–3   : Ping time in seconds since 1970-01-01 (UINT32)
      * Bytes 4–7   : Starting depth / window offset in samples (UINT32)
      * Bytes 8–11  : Ping number (UINT32)
      * Bytes 50–51 : Heading in 0.01 degrees [0..36000] (UINT16)
      * Bytes 80–83 : Longitude / X coordinate (INT32)
      * Bytes 84–87 : Latitude / Y coordinate (INT32)
      * Bytes 88–89 : Coordinate units (INT16: 1=mm, 2=10^-4 min of arc, 3=dm)
      * Bytes 114–115: Number of samples in trace (UINT16)
      * Bytes 116–119: Sampling interval in nanoseconds (UINT32)
      * Bytes 136–139: Depth in millimeters (INT32)
      * Bytes 144–147: Altitude in millimeters (INT32)
      * Bytes 168–169: Weighting factor N (INT16, scaled = raw * 2^(-N))
      * Bytes 200–203: Milliseconds today (UINT32, modulo 1000 = ms of second)
      * Following 240 bytes: Raw acoustic sample array (16-bit integers)
"""

import io
import math
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, Generator, List, Optional, Set, Tuple, Union

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

# -----------------------------------------------------------------------------
# Binary Structures & Signatures
# -----------------------------------------------------------------------------

JSF_MAGIC_MARKER: int = 0x1601
JSF_MSG_HDR_LEN: int = 16
JSF_MSG_HDR_FMT: str = "<HBBHBBBBHI"

# Recognized JSF Message Types
JSF_MSG_SONAR_DATA: int = 80
JSF_MSG_SYSTEM_TIME: int = 82
JSF_MSG_PITCH_ROLL: int = 2020
JSF_MSG_NAVIGATION: int = 2040
JSF_MSG_DVL: int = 2080
JSF_MSG_NMEA_STRING: int = 2002

# 240-byte Sonar Trace Header format
JSF_TRACE_HDR_LEN: int = 240
JSF_TRACE_HDR_FMT: str = "<III38sH28siih24sHI16si4si20sh30sI36s"

# Sound speed nominal fallback in seawater (m/s)
NOMINAL_SOUND_SPEED_MPS: float = 1500.0


class JsfSonarParser(BaseSonarParser):
    """
    Parser implementation for EdgeTech Just Sonar File (.jsf) streams.
    Extracts telemetry, navigation fixes, channel descriptors, and acoustic rasters.
    """

    # -------------------------------------------------------------------------
    # Format Validation
    # -------------------------------------------------------------------------

    def validate(self, source: Union[str, Path, BinaryIO, bytes]) -> bool:
        """
        Validate whether the given binary source is an EdgeTech JSF file.
        Checks for the 0x1601 start-of-header marker and valid 16-byte message framing.
        """
        try:
            with open_binary_source(source) as stream:
                stream.seek(0, io.SEEK_END)
                file_size = stream.tell()
                if file_size < JSF_MSG_HDR_LEN:
                    return False

                stream.seek(0)
                messages_checked = 0
                while stream.tell() < file_size:
                    pos = stream.tell()
                    remaining = file_size - pos
                    if remaining < JSF_MSG_HDR_LEN:
                        return False

                    hdr_bytes = stream.read(JSF_MSG_HDR_LEN)
                    if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                        return False

                    marker, protocol, session, msg_type, cmd, subsystem, channel, seq, reserved, byte_count = struct.unpack(
                        JSF_MSG_HDR_FMT, hdr_bytes
                    )
                    if marker != JSF_MAGIC_MARKER:
                        return False

                    # Byte count must not be negative and cannot exceed remaining file length
                    if byte_count < 0 or remaining < (JSF_MSG_HDR_LEN + byte_count):
                        return False

                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)
                    messages_checked += 1
                    # Inspect first 5 messages to avoid traversing gigabyte files during validation
                    if messages_checked >= 5:
                        break

                return messages_checked > 0
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Header & Stream Metadata
    # -------------------------------------------------------------------------

    def parse_header(self, source: Union[str, Path, BinaryIO, bytes]) -> SonarFileMetadata:
        """
        Scan JSF messages to aggregate file size, message counts, channel descriptors,
        and navigation availability without loading full acoustic payloads into memory.
        """
        filename = "unknown.jsf"
        if isinstance(source, (str, Path)):
            filename = Path(source).name

        warnings: List[str] = []

        with open_binary_source(source) as stream:
            stream.seek(0, io.SEEK_END)
            file_size = stream.tell()
            if file_size < JSF_MSG_HDR_LEN:
                raise SonarCorruptFileError(f"File size ({file_size} bytes) is smaller than JSF message header (16 bytes).")

            stream.seek(0)
            first_marker_bytes = stream.read(2)
            if len(first_marker_bytes) < 2 or struct.unpack("<H", first_marker_bytes)[0] != JSF_MAGIC_MARKER:
                raise SonarFormatError(f"Not a valid JSF file: missing start-of-header marker 0x1601.")

            stream.seek(0)
            unique_ping_numbers: Set[int] = set()
            channels_detected: Dict[int, Dict[str, Any]] = {}
            has_valid_nav = False
            total_messages = 0
            sonar_messages = 0

            while True:
                pos = stream.tell()
                hdr_bytes = stream.read(JSF_MSG_HDR_LEN)
                if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                    if len(hdr_bytes) > 0:
                        warnings.append(f"Truncated message header ({len(hdr_bytes)} bytes) at offset {pos}; stopped scan.")
                    break

                marker, protocol, session, msg_type, cmd, subsystem, channel, seq, reserved, byte_count = struct.unpack(
                    JSF_MSG_HDR_FMT, hdr_bytes
                )

                if marker != JSF_MAGIC_MARKER:
                    warnings.append(f"Corrupt message sync (0x{marker:04X}) at offset {pos}; aborting header scan.")
                    break

                if byte_count < 0:
                    raise SonarCorruptFileError(f"Negative byte count ({byte_count}) at offset {pos}.")

                total_messages += 1

                if msg_type == JSF_MSG_SONAR_DATA and byte_count >= JSF_TRACE_HDR_LEN:
                    sonar_messages += 1
                    trace_hdr_bytes = stream.read(JSF_TRACE_HDR_LEN)
                    if len(trace_hdr_bytes) == JSF_TRACE_HDR_LEN:
                        u_trace = struct.unpack(JSF_TRACE_HDR_FMT, trace_hdr_bytes)
                        p_num = u_trace[2]
                        unique_ping_numbers.add(p_num)

                        num_samples = u_trace[10]
                        interval_ns = u_trace[11]

                        # Track channels
                        if channel not in channels_detected:
                            ch_name = "port" if channel == 0 else ("starboard" if channel == 1 else f"channel_{channel}")
                            channels_detected[channel] = {
                                "channel_id": channel,
                                "channel_name": ch_name,
                                "max_samples": num_samples,
                                "interval_ns": interval_ns,
                            }
                        else:
                            if num_samples > channels_detected[channel]["max_samples"]:
                                channels_detected[channel]["max_samples"] = num_samples

                        # Check navigation
                        if not has_valid_nav:
                            nav = self._extract_nav_from_trace(u_trace)
                            if nav and (nav.latitude is not None or nav.longitude is not None):
                                has_valid_nav = True

                    # Skip sample payload
                    sample_bytes_len = byte_count - JSF_TRACE_HDR_LEN
                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)
                else:
                    # Skip payload of other messages
                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)

            # Build channel info objects
            channel_infos: List[SonarChannelInfo] = []
            for ch_id in sorted(channels_detected.keys()):
                info = channels_detected[ch_id]
                s_count = info["max_samples"]
                i_ns = info["interval_ns"]
                range_m = None
                if s_count > 0 and i_ns > 0:
                    range_m = round((s_count * (i_ns * 1e-9) * NOMINAL_SOUND_SPEED_MPS) / 2.0, 2)

                channel_infos.append(
                    SonarChannelInfo(
                        channel_id=ch_id,
                        channel_name=info["channel_name"],
                        frequency_hz=None,  # Not fabricated
                        sample_count=s_count if s_count > 0 else None,
                        range_m=range_m,
                        sample_format="uint16",
                        available=True,
                    )
                )

            total_pings = len(unique_ping_numbers) if unique_ping_numbers else (sonar_messages // max(len(channels_detected), 1))

            if sonar_messages == 0:
                warnings.append("No Message 80 sonar acoustic data packets found in file.")

            return SonarFileMetadata(
                filename=filename,
                format=SonarFormat.JSF.value,
                file_size_bytes=file_size,
                total_pings=total_pings,
                channel_count=len(channel_infos),
                channels=channel_infos,
                navigation_available=has_valid_nav,
                warnings=warnings,
            )

    # -------------------------------------------------------------------------
    # Telemetry Extraction
    # -------------------------------------------------------------------------

    def extract_telemetry(self, source: Union[str, Path, BinaryIO, bytes]) -> Optional[SonarNavigation]:
        """
        Extract the first valid non-sentinel navigation fix from the JSF stream.
        Strictly outputs None if no valid GPS or sensor data exists.
        """
        with open_binary_source(source) as stream:
            stream.seek(0)
            while True:
                pos = stream.tell()
                hdr_bytes = stream.read(JSF_MSG_HDR_LEN)
                if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                    break

                marker, _, _, msg_type, _, _, _, _, _, byte_count = struct.unpack(JSF_MSG_HDR_FMT, hdr_bytes)
                if marker != JSF_MAGIC_MARKER or byte_count < 0:
                    break

                if msg_type == JSF_MSG_SONAR_DATA and byte_count >= JSF_TRACE_HDR_LEN:
                    trace_hdr_bytes = stream.read(JSF_TRACE_HDR_LEN)
                    if len(trace_hdr_bytes) == JSF_TRACE_HDR_LEN:
                        u_trace = struct.unpack(JSF_TRACE_HDR_FMT, trace_hdr_bytes)
                        nav = self._extract_nav_from_trace(u_trace)
                        if nav and (nav.latitude is not None or nav.longitude is not None or nav.heading_deg is not None):
                            return nav

                stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)

        return None

    # -------------------------------------------------------------------------
    # Ping Parsing
    # -------------------------------------------------------------------------

    def parse_pings(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
    ) -> List[SonarPingTelemetry]:
        """
        Parse per-ping telemetry streams up to max_pings without buffering sample rasters.
        Groups channel messages sharing the same ping number into a single ping record.
        """
        telemetries: List[SonarPingTelemetry] = []

        with open_binary_source(source) as stream:
            stream.seek(0)
            current_ping_num: Optional[int] = None
            current_nav: Optional[SonarNavigation] = None
            current_ts: Optional[str] = None
            seen_channels_in_ping: Set[int] = set()
            pings_emitted = 0

            def emit_current_ping() -> bool:
                nonlocal pings_emitted, current_ping_num, current_nav, current_ts, seen_channels_in_ping
                if current_ping_num is not None or seen_channels_in_ping:
                    lat = current_nav.latitude if current_nav else None
                    lon = current_nav.longitude if current_nav else None
                    hdg = current_nav.heading_deg if current_nav else None
                    alt = current_nav.altitude_m if current_nav else None
                    dep = current_nav.depth_m if current_nav else None

                    telemetries.append(
                        SonarPingTelemetry(
                            ping_index=pings_emitted,
                            timestamp=current_ts,
                            latitude=lat,
                            longitude=lon,
                            heading_deg=hdg,
                            altitude_m=alt,
                            depth_m=dep,
                        )
                    )
                    pings_emitted += 1
                    seen_channels_in_ping.clear()
                    current_nav = None
                    current_ts = None
                    if max_pings is not None and pings_emitted >= max_pings:
                        return True
                return False

            while True:
                if max_pings is not None and pings_emitted >= max_pings:
                    break

                pos = stream.tell()
                hdr_bytes = stream.read(JSF_MSG_HDR_LEN)
                if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                    break

                marker, _, _, msg_type, _, _, channel, _, _, byte_count = struct.unpack(JSF_MSG_HDR_FMT, hdr_bytes)
                if marker != JSF_MAGIC_MARKER or byte_count < 0:
                    break

                if msg_type == JSF_MSG_SONAR_DATA and byte_count >= JSF_TRACE_HDR_LEN:
                    trace_hdr_bytes = stream.read(JSF_TRACE_HDR_LEN)
                    if len(trace_hdr_bytes) == JSF_TRACE_HDR_LEN:
                        u_trace = struct.unpack(JSF_TRACE_HDR_FMT, trace_hdr_bytes)
                        p_num = u_trace[2]

                        # Detect ping boundary: changed ping number or duplicated channel
                        if (current_ping_num is not None and p_num != current_ping_num) or (channel in seen_channels_in_ping):
                            if emit_current_ping():
                                break

                        current_ping_num = p_num
                        seen_channels_in_ping.add(channel)

                        nav = self._extract_nav_from_trace(u_trace)
                        if nav and current_nav is None:
                            current_nav = nav

                        if current_ts is None and nav and nav.timestamp:
                            current_ts = nav.timestamp

                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)
                else:
                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)

            # Emit trailing ping
            if max_pings is None or pings_emitted < max_pings:
                emit_current_ping()

        return telemetries

    # -------------------------------------------------------------------------
    # Waterfall Raster Construction
    # -------------------------------------------------------------------------

    def build_waterfall_raster(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Assemble JSF Message 80 acoustic returns into a normalized 2D raster.
        Delegates scanline normalization and nadir alignment to SonarRasterBuilder.
        """
        pings_channels: List[Dict[int, np.ndarray]] = []
        slant_ranges: List[Optional[float]] = []

        with open_binary_source(source) as stream:
            stream.seek(0, io.SEEK_END)
            file_size = stream.tell()
            if file_size < JSF_MSG_HDR_LEN:
                raise SonarCorruptFileError("Cannot build raster: JSF file is truncated.")

            stream.seek(0)
            first_marker_bytes = stream.read(2)
            if len(first_marker_bytes) < 2 or struct.unpack("<H", first_marker_bytes)[0] != JSF_MAGIC_MARKER:
                raise SonarFormatError("Not a valid JSF file: missing start marker 0x1601.")

            stream.seek(0)
            current_ping_num: Optional[int] = None
            current_ping_dict: Dict[int, np.ndarray] = {}
            current_ping_slant_range: Optional[float] = None
            seen_channels_in_ping: Set[int] = set()
            pings_collected = 0

            def commit_ping() -> bool:
                nonlocal pings_collected, current_ping_num, current_ping_dict, current_ping_slant_range, seen_channels_in_ping
                if current_ping_dict or current_ping_num is not None:
                    pings_channels.append(dict(current_ping_dict))
                    slant_ranges.append(current_ping_slant_range)
                    pings_collected += 1
                    current_ping_dict.clear()
                    seen_channels_in_ping.clear()
                    current_ping_slant_range = None
                    if max_pings is not None and pings_collected >= max_pings:
                        return True
                return False

            while True:
                if max_pings is not None and pings_collected >= max_pings:
                    break

                pos = stream.tell()
                hdr_bytes = stream.read(JSF_MSG_HDR_LEN)
                if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                    if len(hdr_bytes) > 0:
                        raise SonarCorruptFileError(f"Corrupt JSF stream: truncated message header at offset {pos}.")
                    break

                marker, _, _, msg_type, _, _, channel, _, _, byte_count = struct.unpack(JSF_MSG_HDR_FMT, hdr_bytes)
                if marker != JSF_MAGIC_MARKER or byte_count < 0:
                    raise SonarCorruptFileError(f"Corrupt JSF message at offset {pos}: marker 0x{marker:04X}, byte_count {byte_count}.")

                if pos + JSF_MSG_HDR_LEN + byte_count > file_size:
                    raise SonarCorruptFileError(
                        f"Corrupt JSF stream: message at offset {pos} extends beyond end of file ({file_size} bytes)."
                    )

                if msg_type == JSF_MSG_SONAR_DATA:
                    if byte_count < JSF_TRACE_HDR_LEN:
                        raise SonarCorruptFileError(f"Corrupt Message 80: payload size ({byte_count}) < 240 bytes.")

                    trace_hdr_bytes = stream.read(JSF_TRACE_HDR_LEN)
                    if len(trace_hdr_bytes) < JSF_TRACE_HDR_LEN:
                        raise SonarCorruptFileError(f"Corrupt Message 80: truncated trace header at offset {pos}.")

                    u_trace = struct.unpack(JSF_TRACE_HDR_FMT, trace_hdr_bytes)
                    p_num = u_trace[2]
                    num_samples = u_trace[10]
                    interval_ns = u_trace[11]
                    weighting_factor = u_trace[17]

                    # Read raw acoustic samples
                    sample_bytes_len = byte_count - JSF_TRACE_HDR_LEN
                    raw_sample_bytes = stream.read(sample_bytes_len)

                    if len(raw_sample_bytes) == sample_bytes_len and sample_bytes_len >= 2:
                        samples = np.frombuffer(raw_sample_bytes, dtype=np.uint16)
                        if weighting_factor != 0:
                            float_samples = samples.astype(np.float32) * (2.0 ** (-weighting_factor))
                        else:
                            float_samples = samples.astype(np.float32)

                        # Detect ping boundary
                        if (current_ping_num is not None and p_num != current_ping_num) or (channel in seen_channels_in_ping):
                            if commit_ping():
                                break

                        current_ping_num = p_num
                        seen_channels_in_ping.add(channel)
                        current_ping_dict[channel] = float_samples

                        if current_ping_slant_range is None and num_samples > 0 and interval_ns > 0:
                            calc_range = (num_samples * (interval_ns * 1e-9) * NOMINAL_SOUND_SPEED_MPS) / 2.0
                            if calc_range > 0:
                                current_ping_slant_range = calc_range

                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)
                else:
                    stream.seek(pos + JSF_MSG_HDR_LEN + byte_count)

            # Commit trailing ping
            if max_pings is None or pings_collected < max_pings:
                commit_ping()

        raster, spatial_metadata = SonarRasterBuilder.assemble_scanlines(
            pings_channels=pings_channels,
            requested_channels=channels,
            slant_ranges=slant_ranges,
            max_pings=max_pings,
        )
        spatial_metadata["format"] = "JSF"
        return raster, spatial_metadata

    # -------------------------------------------------------------------------
    # Helper: Navigation & Sentinel Validation
    # -------------------------------------------------------------------------

    def _extract_nav_from_trace(self, u_trace: tuple) -> Optional[SonarNavigation]:
        """
        Extract coordinates, heading, altitude, and depth from unpacked 240-byte trace header.
        Applies rigorous sentinel filtering:
          - (0, 0) coordinates treated as unpopulated / missing.
          - Projected coordinates (mm, dm) are not converted to WGS84.
          - Coordinates in 10^-4 minutes of arc (coord_units == 2) converted via val / 600,000.
          - Sentinel / negative values for heading, altitude, and depth strictly converted to None.
        """
        ping_time = u_trace[0]
        heading_raw = u_trace[4]
        x_coord = u_trace[6]
        y_coord = u_trace[7]
        coord_units = u_trace[8]
        depth_mm = u_trace[13]
        altitude_mm = u_trace[15]
        ms_today = u_trace[19]

        lat: Optional[float] = None
        lon: Optional[float] = None

        # Geodetic coordinates (unit code 2 = minutes of arc * 10^-4)
        if coord_units == 2:
            if not self._is_sentinel_int(x_coord) and not self._is_sentinel_int(y_coord):
                # (0, 0) is treated as unpopulated Null Island
                if not (x_coord == 0 and y_coord == 0):
                    eval_lon = x_coord / 600000.0
                    eval_lat = y_coord / 600000.0
                    if -90.0 <= eval_lat <= 90.0 and -180.0 <= eval_lon <= 180.0:
                        lat = round(eval_lat, 7)
                        lon = round(eval_lon, 7)

        # Heading: 0.01 degrees (0..36000)
        heading_deg: Optional[float] = None
        if 0 < heading_raw <= 36000 and heading_raw != 0xFFFF:
            heading_deg = round(heading_raw / 100.0, 2)

        # Altitude: millimeters off seabed
        altitude_m: Optional[float] = None
        if 100 <= altitude_mm <= 10000000 and not self._is_sentinel_int(altitude_mm):
            altitude_m = round(altitude_mm / 1000.0, 3)

        # Depth: millimeters below sea surface
        depth_m: Optional[float] = None
        if 0 <= depth_mm <= 12000000 and not self._is_sentinel_int(depth_mm):
            depth_m = round(depth_mm / 1000.0, 3)

        # Timestamp
        ts_str: Optional[str] = None
        if ping_time > 0:
            try:
                dt = datetime.fromtimestamp(ping_time, tz=timezone.utc)
                if ms_today > 0:
                    ms = ms_today % 1000
                    dt = dt.replace(microsecond=ms * 1000)
                ts_str = dt.isoformat()
            except (ValueError, OSError):
                ts_str = None

        return SonarNavigation(
            timestamp=ts_str,
            latitude=lat,
            longitude=lon,
            heading_deg=heading_deg,
            altitude_m=altitude_m,
            depth_m=depth_m,
            source="jsf_trace_header",
        )

    @staticmethod
    def _is_sentinel_int(val: int) -> bool:
        """Check if integer represents common sentinel / fill values."""
        return val in (-999, -9999, -1, 0x7FFFFFFF, -2147483648)
