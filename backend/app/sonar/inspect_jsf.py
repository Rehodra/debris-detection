#!/usr/bin/env python3
"""
Diagnostic Inspection Utility for EdgeTech Just Sonar File (.jsf) streams.

Usage:
    python inspect_jsf.py <path-to-file.jsf>
"""

import struct
import sys
from pathlib import Path
from typing import Dict

import numpy as np

# Support direct script execution by adding app directory to path
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parents[1] if script_dir.name == "sonar" else script_dir
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.sonar.jsf_reader import (
    JsfSonarParser,
    JSF_MAGIC_MARKER,
    JSF_MSG_HDR_FMT,
    JSF_MSG_HDR_LEN,
    JSF_MSG_SONAR_DATA,
    JSF_MSG_SYSTEM_TIME,
    JSF_MSG_PITCH_ROLL,
    JSF_MSG_NAVIGATION,
    JSF_MSG_DVL,
    JSF_MSG_NMEA_STRING,
)


def inspect_jsf(file_path_str: str) -> None:
    path = Path(file_path_str)
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    parser = JsfSonarParser()
    is_valid = parser.validate(path)

    print("=" * 65)
    print(" MarineScan — EdgeTech JSF Sonar Diagnostic Inspector")
    print("=" * 65)
    print(f" Target File       : {path.name}")
    print(f" Absolute Path     : {path.resolve()}")
    print(f" File Size (bytes) : {path.stat().st_size:,} bytes ({path.stat().st_size / (1024 * 1024):.2f} MB)")
    print(f" JSF Signature     : {'VALID (0x1601 detected)' if is_valid else 'INVALID (not a recognized JSF file)'}")

    if not is_valid:
        print("\n[ABORT] The specified file failed JSF format validation.")
        return

    # 1. Header Metadata Scan
    print("\n--- Header Metadata ---")
    meta = parser.parse_header(path)
    print(f" Format            : {meta.format}")
    print(f" Declared Channels : {meta.channel_count}")
    print(f" Total Sonar Pings : {meta.total_pings:,}")
    print(f" GPS Nav Available : {'YES' if meta.navigation_available else 'NO (or uncalibrated)'}")

    if meta.warnings:
        print(" Warnings          :")
        for w in meta.warnings:
            print(f"   - {w}")

    # 2. Channel Breakdown
    print("\n--- Channel Information ---")
    for ch in meta.channels:
        freq_str = f"{ch.frequency_hz / 1000.0:.1f} kHz" if ch.frequency_hz else "N/A"
        range_str = f"{ch.range_m:.1f} m" if ch.range_m else "N/A"
        samples_str = f"{ch.sample_count} samples" if ch.sample_count else "N/A"
        print(f" Channel {ch.channel_id:2d}: {ch.channel_name:<12} | Samples: {samples_str:<14} | Range: {range_str:<10} | Freq: {freq_str:<10}")

    # 3. Message Type Distribution
    message_counts: Dict[str, int] = {
        "Sonar Data (80)": 0,
        "System Time (82)": 0,
        "Pitch/Roll (2020)": 0,
        "Navigation (2040)": 0,
        "DVL (2080)": 0,
        "NMEA (2002)": 0,
        "Other": 0,
    }

    with open(path, "rb") as f:
        while True:
            pos = f.tell()
            hdr_bytes = f.read(JSF_MSG_HDR_LEN)
            if len(hdr_bytes) < JSF_MSG_HDR_LEN:
                break

            marker, _, _, msg_type, _, _, _, _, _, byte_count = struct.unpack(JSF_MSG_HDR_FMT, hdr_bytes)
            if marker != JSF_MAGIC_MARKER or byte_count < 0:
                break

            if msg_type == JSF_MSG_SONAR_DATA:
                message_counts["Sonar Data (80)"] += 1
            elif msg_type == JSF_MSG_SYSTEM_TIME:
                message_counts["System Time (82)"] += 1
            elif msg_type == JSF_MSG_PITCH_ROLL:
                message_counts["Pitch/Roll (2020)"] += 1
            elif msg_type == JSF_MSG_NAVIGATION:
                message_counts["Navigation (2040)"] += 1
            elif msg_type == JSF_MSG_DVL:
                message_counts["DVL (2080)"] += 1
            elif msg_type == JSF_MSG_NMEA_STRING:
                message_counts["NMEA (2002)"] += 1
            else:
                message_counts["Other"] += 1

            f.seek(pos + JSF_MSG_HDR_LEN + byte_count)

    print("\n--- Message Packet Distribution ---")
    for name, count in message_counts.items():
        if count > 0:
            print(f" {name:<22}: {count:,}")

    # 4. Telemetry & Navigation Sample
    print("\n--- Telemetry & Sensor Availability ---")
    telemetry = parser.extract_telemetry(path)
    if telemetry:
        lat_str = f"{telemetry.latitude:.7f}°" if telemetry.latitude is not None else "None"
        lon_str = f"{telemetry.longitude:.7f}°" if telemetry.longitude is not None else "None"
        hdg_str = f"{telemetry.heading_deg:.2f}°" if telemetry.heading_deg is not None else "None"
        alt_str = f"{telemetry.altitude_m:.2f} m" if telemetry.altitude_m is not None else "None"
        dep_str = f"{telemetry.depth_m:.2f} m" if telemetry.depth_m is not None else "None"
        ts_str = telemetry.timestamp if telemetry.timestamp else "None"

        print(f" Timestamp         : {ts_str}")
        print(f" Latitude / Long   : {lat_str} / {lon_str}")
        print(f" Sensor Heading    : {hdg_str}")
        print(f" Towfish Altitude  : {alt_str}")
        print(f" Sensor Depth      : {dep_str}")
    else:
        print(" Telemetry Record  : No non-null GPS or heading telemetry logged.")

    # 5. Waterfall Assembly Verification (Sample first 10 pings)
    print("\n--- Waterfall Raster Generation ---")
    try:
        raster, r_meta = parser.build_waterfall_raster(path, max_pings=10)
        print(f" Raster Dimensions : {raster.shape[0]} pings (rows) × {raster.shape[1]} range bins (cols)")
        print(f" Data Type / Range : {raster.dtype} [{raster.min()}, {raster.max()}]")
        print(f" Nadir Position    : {r_meta.get('nadir_pixel_x', 'N/A')}")
        print(f" Channel Layout    : {r_meta.get('channel_layout', 'N/A')}")
        res_str = f"{r_meta['meters_per_pixel']:.4f} m/px" if r_meta.get("meters_per_pixel") else "None (unrecorded)"
        print(f" Spatial Res.      : {res_str}")
        print(" Raster Status     : SUCCESS")
    except Exception as exc:
        print(f" Raster Status     : FAILED ({exc})")

    print("=" * 65)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_jsf.py <path-to-file.jsf>")
        sys.exit(1)
    inspect_jsf(sys.argv[1])
