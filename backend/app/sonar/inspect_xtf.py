#!/usr/bin/env python3
"""
Diagnostic Inspection Utility for Extended Triton Format (.xtf) files.

Usage:
    python inspect_xtf.py <path-to-file.xtf>
"""

import sys
import struct
from pathlib import Path
from typing import Dict

import numpy as np

# Support direct script execution by adding app directory to path
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parents[1] if script_dir.name == "sonar" else script_dir
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.sonar.xtf_reader import (
    XtfSonarParser,
    XTF_PACKET_HDR_FMT,
    XTF_PACKET_HDR_LEN,
    XTF_PACKET_MAGIC,
    XTF_HEADER_SONAR,
    XTF_HEADER_ANNOTATION,
    XTF_HEADER_ATTITUDE,
    XTF_HEADER_POSITION,
    XTF_HEADER_BATHYMETRY,
)


def inspect_xtf(file_path_str: str) -> None:
    path = Path(file_path_str)
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        sys.exit(1)

    parser = XtfSonarParser()
    is_valid = parser.validate(path)

    print("=" * 65)
    print(" MarineScan — XTF Sonar File Diagnostic Inspector")
    print("=" * 65)
    print(f" Target File       : {path.name}")
    print(f" Absolute Path     : {path.resolve()}")
    print(f" File Size (bytes) : {path.stat().st_size:,} bytes ({path.stat().st_size / (1024 * 1024):.2f} MB)")
    print(f" XTF Signature     : {'VALID (0x7B detected)' if is_valid else 'INVALID (not a recognized XTF file)'}")

    if not is_valid:
        print("\n[ABORT] The specified file failed XTF format validation.")
        return

    # 1. Header Information
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
        print(f" Channel {ch.channel_id:2d}: {ch.channel_name:<12} | Format: {ch.sample_format:<8} | Freq: {freq_str:<10} | Active: {ch.available}")

    # 3. Packet Scan & Distribution
    packet_counts: Dict[str, int] = {
        "Sidescan (0)": 0,
        "Annotation (1)": 0,
        "Position (2)": 0,
        "Attitude (3)": 0,
        "Bathymetry (4)": 0,
        "Other": 0,
    }

    with open(path, "rb") as f:
        f.seek(1024)
        while True:
            pkt_pos = f.tell()
            pkt_bytes = f.read(XTF_PACKET_HDR_LEN)
            if len(pkt_bytes) < XTF_PACKET_HDR_LEN:
                break

            magic, hdr_type, _, _, _, _, num_bytes = struct.unpack(XTF_PACKET_HDR_FMT, pkt_bytes)
            if (magic & 0xFFFF) != XTF_PACKET_MAGIC or num_bytes < XTF_PACKET_HDR_LEN:
                break

            if hdr_type == XTF_HEADER_SONAR:
                packet_counts["Sidescan (0)"] += 1
            elif hdr_type == XTF_HEADER_ANNOTATION:
                packet_counts["Annotation (1)"] += 1
            elif hdr_type == XTF_HEADER_POSITION:
                packet_counts["Position (2)"] += 1
            elif hdr_type == XTF_HEADER_ATTITUDE:
                packet_counts["Attitude (3)"] += 1
            elif hdr_type == XTF_HEADER_BATHYMETRY:
                packet_counts["Bathymetry (4)"] += 1
            else:
                packet_counts["Other"] += 1

            f.seek(pkt_pos + num_bytes)

    print("\n--- Packet Distribution ---")
    for p_type, count in packet_counts.items():
        if count > 0:
            print(f"  {p_type:<18}: {count:,} packets")

    # 4. Telemetry & Navigation Sample
    print("\n--- Navigation & Sensor Telemetry ---")
    nav = parser.extract_telemetry(path)
    first_pings = parser.parse_pings(path, max_pings=1)

    first_timestamp = first_pings[0].timestamp if first_pings else None
    print(f" First Timestamp   : {first_timestamp or 'N/A'}")

    if nav and nav.latitude is not None and nav.longitude is not None:
        print(f" First GPS Fix     : Lat {nav.latitude:.6f}°, Lon {nav.longitude:.6f}° (Source: {nav.source})")
    else:
        print(" First GPS Fix     : None (Coordinates absent, projected, or sentinel)")

    print(f" Heading Available : {'YES (' + str(nav.heading_deg) + '°)' if nav and nav.heading_deg is not None else 'NO'}")
    print(f" Altitude Available: {'YES (' + str(nav.altitude_m) + ' m)' if nav and nav.altitude_m is not None else 'NO'}")
    print(f" Depth Available   : {'YES (' + str(nav.depth_m) + ' m)' if nav and nav.depth_m is not None else 'NO'}")

    # 5. Acoustic Raster Statistics
    print("\n--- Acoustic Raster Inspection ---")
    raster, spatial = parser.build_waterfall_raster(path, max_pings=50)
    if raster.size > 0:
        print(f" Rendered Shape    : {raster.shape[0]} pings × {raster.shape[1]} samples")
        print(f" Nadir Column      : {spatial.get('nadir_pixel_x', 'N/A')}")
        print(f" Resolution (GSD)  : {spatial.get('meters_per_pixel', 'N/A')} m/pixel")
        print(f" Min Intensity     : {int(np.min(raster))}")
        print(f" Max Intensity     : {int(np.max(raster))}")
        print(f" Mean Intensity    : {float(np.mean(raster)):.2f}")
    else:
        print(" Acoustic raster   : Empty (no sidescan samples recovered)")

    print("=" * 65)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_xtf.py <path-to-file.xtf>")
        sys.exit(1)

    inspect_xtf(sys.argv[1])
