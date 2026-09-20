#!/usr/bin/env python3
"""Convenience runner for XTF inspection utility."""
import sys
from pathlib import Path

# Ensure backend root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.sonar.inspect_xtf import inspect_xtf

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_xtf.py <path-to-file.xtf>")
        sys.exit(1)
    inspect_xtf(sys.argv[1])
