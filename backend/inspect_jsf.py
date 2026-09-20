#!/usr/bin/env python3
"""
Thin CLI entrypoint for MarineScan EdgeTech JSF Inspector.
Usage:
    python inspect_jsf.py <path-to-file.jsf>
"""

import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.sonar.inspect_jsf import inspect_jsf

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_jsf.py <path-to-file.jsf>")
        sys.exit(1)
    inspect_jsf(sys.argv[1])
