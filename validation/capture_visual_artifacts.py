#!/usr/bin/env python3
"""
Generate and export visual inspection artifacts to validation/screenshots/.
Saves lossless waterfall rasters, visual overlays, and UI artifact captures.
"""

import sys
from pathlib import Path
import cv2
import numpy as np
from fastapi.testclient import TestClient

# Set up paths
backend_dir = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_dir))

from app.main import app
from app.sonar.xtf_reader import XtfSonarParser
from app.sonar.jsf_reader import JsfSonarParser

client = TestClient(app)
screenshots_dir = Path(__file__).resolve().parent / "screenshots"
screenshots_dir.mkdir(parents=True, exist_ok=True)
datasets_dir = Path(__file__).resolve().parent / "datasets"

# 1. Real XTF Small Raster Capture
print("[*] Generating waterfall_xtf_small.png...")
xtf_small_path = datasets_dir / "xtf" / "15CCT03_SSS_153_150602154100.xtf"
if xtf_small_path.exists():
    parser = XtfSonarParser()
    raster, meta = parser.build_waterfall_raster(xtf_small_path)
    # Scale width for clear visual artifact inspectability if needed, or save exact raster
    cv2.imwrite(str(screenshots_dir / "waterfall_xtf_small.png"), raster)
    print(f"    Saved: {raster.shape}")

# 2. Real XTF Medium Raster Capture
print("[*] Generating waterfall_xtf_medium.png...")
xtf_med_path = datasets_dir / "xtf" / "15CCT03_SSS_153_150602154200.xtf"
if xtf_med_path.exists():
    parser = XtfSonarParser()
    raster, meta = parser.build_waterfall_raster(xtf_med_path, max_pings=150)
    cv2.imwrite(str(screenshots_dir / "waterfall_xtf_medium.png"), raster)
    print(f"    Saved: {raster.shape}")

# 3. Synthetic JSF Medium Raster Capture
print("[*] Generating waterfall_jsf_medium.png...")
jsf_med_path = datasets_dir / "jsf" / "synthetic_medium.jsf"
if jsf_med_path.exists():
    parser = JsfSonarParser()
    raster, meta = parser.build_waterfall_raster(jsf_med_path)
    cv2.imwrite(str(screenshots_dir / "waterfall_jsf_medium.png"), raster)
    print(f"    Saved: {raster.shape}")

# 4. Master Visual Overlay for Lucinda van Valkenburg Shipwreck
print("[*] Generating overlay_lucinda_shipwreck.jpg...")
lucinda_path = datasets_dir / "sample_images" / "Lucinda_van_Valkenburg_06.png"
if lucinda_path.exists():
    with open(lucinda_path, "rb") as f:
        resp = client.post("/api/v1/analyses/visualize", files={"file": ("lucinda.png", f.read(), "image/png")})
    if resp.status_code == 200:
        (screenshots_dir / "overlay_lucinda_shipwreck.jpg").write_bytes(resp.content)
        print("    Saved overlay_lucinda_shipwreck.jpg")

# 5. Master Visual Overlay for Viator Shipwreck
print("[*] Generating overlay_viator_shipwreck.jpg...")
viator_path = datasets_dir / "sample_images" / "Viator_11.png"
if viator_path.exists():
    with open(viator_path, "rb") as f:
        resp = client.post("/api/v1/analyses/visualize", files={"file": ("viator.png", f.read(), "image/png")})
    if resp.status_code == 200:
        (screenshots_dir / "overlay_viator_shipwreck.jpg").write_bytes(resp.content)
        print("    Saved overlay_viator_shipwreck.jpg")

print("[+] Visual screenshots and raster artifacts generated successfully.")
