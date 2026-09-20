#!/usr/bin/env python3
"""
Generate test datasets for Phase 15 End-to-End System Validation:
- synthetic_small.jsf (10 pings, full GPS & telemetry)
- synthetic_medium.jsf (60 pings, dual channel, heading, altitude, depth)
- corrupt_marker.jsf (invalid magic marker)
- null_island.jsf (sentinel 0.0, 0.0 coordinates)
- corrupt_header.xtf (corrupted XTF header)
- truncated.xtf (truncated ping data)
"""

import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

from app.tests.test_jsf_parser import build_synthetic_jsf_binary
from app.tests.test_xtf_parser import build_synthetic_xtf_binary

datasets_dir = Path(__file__).resolve().parent / "datasets"
jsf_dir = datasets_dir / "jsf"
xtf_dir = datasets_dir / "xtf"

jsf_dir.mkdir(parents=True, exist_ok=True)
xtf_dir.mkdir(parents=True, exist_ok=True)

# 1. Synthetic Small JSF
print("[*] Generating synthetic_small.jsf...")
small_jsf = build_synthetic_jsf_binary(
    num_pings=10,
    samples_per_chan=120,
    lat=24.8607,
    lon=67.0011,
    heading=90.0,
    altitude=14.5,
    depth=22.0,
    sample_interval_ns=20000,
)
(jsf_dir / "synthetic_small.jsf").write_bytes(small_jsf)

# 2. Synthetic Medium JSF
print("[*] Generating synthetic_medium.jsf...")
medium_jsf = build_synthetic_jsf_binary(
    num_pings=60,
    samples_per_chan=250,
    lat=13.0524,
    lon=80.4215,
    heading=180.0,
    altitude=16.0,
    depth=35.0,
    sample_interval_ns=20000,
)
(jsf_dir / "synthetic_medium.jsf").write_bytes(medium_jsf)

# 3. Corrupt Marker JSF
print("[*] Generating corrupt_marker.jsf...")
corrupt_jsf = bytearray(small_jsf)
corrupt_jsf[0:2] = b"\x00\x00"  # Break 0x1601 magic marker
(jsf_dir / "corrupt_marker.jsf").write_bytes(corrupt_jsf)

# 4. Null Island JSF (testing sentinel coordinate rejection)
print("[*] Generating null_island.jsf...")
null_island_jsf = build_synthetic_jsf_binary(
    num_pings=8,
    samples_per_chan=100,
    lat=0.0,
    lon=0.0,
    heading=45.0,
    altitude=10.0,
    depth=15.0,
)
(jsf_dir / "null_island.jsf").write_bytes(null_island_jsf)

# 5. Corrupt Header XTF
print("[*] Generating corrupt_header.xtf...")
valid_xtf = build_synthetic_xtf_binary(num_pings=5, samples_per_chan=80)
corrupt_xtf = bytearray(valid_xtf)
corrupt_xtf[0] = 0x00  # Break 0x7B signature
(xtf_dir / "corrupt_header.xtf").write_bytes(corrupt_xtf)

# 6. Truncated XTF
print("[*] Generating truncated.xtf...")
truncated_xtf = valid_xtf[:500]  # Cut off midway through header
(xtf_dir / "truncated.xtf").write_bytes(truncated_xtf)

print("[+] All validation datasets generated successfully.")
