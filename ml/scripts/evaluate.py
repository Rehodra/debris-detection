#!/usr/bin/env python3
"""
MarineScan ML Evaluation & Accuracy Benchmark Script
===================================================
Location: ml/scripts/evaluate.py
Delegates to or runs evaluation of yolo11_sonar_best.pt.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path if needed
backend_dir = Path(__file__).resolve().parent.parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from evaluate_accuracy import main

if __name__ == "__main__":
    main()
