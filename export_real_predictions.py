#!/usr/bin/env python3
"""
SIH26057 — Model Inference & Predictions Exporter Script
Runs YOLO detection + Physics & Shadow verification engine on side-scan sonar imagery
and exports predictions in the exact schema required for the Sanshodhak Chart Room demo.
"""

import os
import sys
import json
import base64
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any

import cv2
import numpy as np

# Ensure backend path is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR
BACKEND_DIR = PROJECT_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("export_predictions")


def create_bbox_thumbnail(
    image_bgr: np.ndarray,
    bbox_dict: Dict[str, float],
    class_name: str,
    confidence: float,
    color_rgb: tuple = (230, 57, 70),
    margin_ratio: float = 0.25,
) -> str:
    """
    Crop bounding box region with margin, draw overlay box & label,
    and return as Base64 JPEG data URI.
    """
    img_h, img_w = image_bgr.shape[:2]

    # Normalize/pixel coordinates
    x_min = int(bbox_dict.get("x_min", 0))
    y_min = int(bbox_dict.get("y_min", 0))
    x_max = int(bbox_dict.get("x_max", img_w))
    y_max = int(bbox_dict.get("y_max", img_h))

    # Add margin
    bw = x_max - x_min
    bh = y_max - y_min
    margin_x = int(bw * margin_ratio)
    margin_y = int(bh * margin_ratio)

    crop_x1 = max(0, x_min - margin_x)
    crop_y1 = max(0, y_min - margin_y)
    crop_x2 = min(img_w, x_max + margin_x)
    crop_y2 = min(img_h, y_max + margin_y)

    crop = image_bgr[crop_y1:crop_y2, crop_x1:crop_x2].copy()

    # Coordinates inside crop
    bx1 = x_min - crop_x1
    by1 = y_min - crop_y1
    bx2 = x_max - crop_x1
    by2 = y_max - crop_y1

    # Color BGR
    color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])

    # Draw bounding box
    cv2.rectangle(crop, (bx1, by1), (bx2, by2), color_bgr, 2)

    # Draw label box
    label_text = f"{class_name} {confidence:.0%}"
    (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    label_y = max(by1 - 4, th + 4)
    cv2.rectangle(crop, (bx1, label_y - th - 4), (bx1 + tw + 6, label_y + 2), color_bgr, -1)
    cv2.putText(crop, label_text, (bx1 + 3, label_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # Encode to JPEG
    success, buffer = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not success:
        return ""

    b64_str = base64.b64encode(buffer.tobytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"


def find_validation_images(images_arg: str) -> List[Path]:
    """Find sonar survey images from argument path or fallback paths."""
    search_paths = []
    if images_arg:
        p = Path(images_arg)
        if p.is_file():
            return [p]
        elif p.is_dir():
            search_paths.append(p)

    # Fallback default locations
    search_paths.extend([
        PROJECT_ROOT / "outputs" / "synthetic_sonar_generator" / "demo_dataset" / "images" / "val",
        PROJECT_ROOT / "outputs" / "synthetic_sonar_generator" / "demo_dataset" / "images" / "train",
        BACKEND_DIR,
    ])

    found_files: List[Path] = []
    valid_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

    for s_path in search_paths:
        if s_path.exists() and s_path.is_dir():
            for root, dirs, files in os.walk(s_path):
                # Exclude .venv, .git, node_modules
                dirs[:] = [d for d in dirs if d not in {".venv", ".git", "node_modules", "site-packages"}]
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in valid_exts and not f.startswith("test_output"):
                        found_files.append(Path(root) / f)

    # Deduplicate by resolved path
    seen = set()
    unique_files = []
    for f in found_files:
        rf = f.resolve()
        if rf not in seen:
            seen.add(rf)
            unique_files.append(f)

    return unique_files


def run_prediction_export(
    weights_path: str,
    images_dir: str,
    out_path: str,
    confidence_thresh: float = 0.20,
) -> List[Dict[str, Any]]:
    """Run master pipeline on validation images and format predictions JSON."""
    from app.services.master_pipeline_service import master_pipeline_service
    from app.ml.model_loader import ModelLoader

    # Pre-resolve model path
    resolved_weights = ModelLoader.resolve_model_path(weights_path)
    logger.info(f"Loading weights from: {resolved_weights}")

    # Discover images
    image_paths = find_validation_images(images_dir)
    if not image_paths:
        logger.warning("No image files found in specified path. Generating synthetic sonar test samples...")
        image_paths = create_fallback_sonar_images()

    logger.info(f"Processing {len(image_paths)} sonar images for handoff predictions...")

    all_detections: List[Dict[str, Any]] = []
    det_counter = 1

    for img_path in image_paths:
        logger.info(f"Analyzing sonar survey image: {img_path.name}")
        try:
            with open(img_path, "rb") as f:
                img_bytes = f.read()

            result = master_pipeline_service.execute_pipeline(
                image_bytes=img_bytes,
                confidence_threshold=confidence_thresh,
                return_visualization=False,
            )

            # Load BGR image for thumbnail cropping
            img_bgr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)

            for target in result.targets:
                det_id = f"DET-{det_counter:03d}"
                det_counter += 1

                # Normalize bbox to [x_center, y_center, width, height] (0 - 1)
                n_xmin = target.bbox.normalized_x_min
                n_ymin = target.bbox.normalized_y_min
                n_xmax = target.bbox.normalized_x_max
                n_ymax = target.bbox.normalized_y_max

                xc = round((n_xmin + n_xmax) / 2.0, 4)
                yc = round((n_ymin + n_ymax) / 2.0, 4)
                w = round(abs(n_xmax - n_xmin), 4)
                h = round(abs(n_ymax - n_ymin), 4)

                # Generate thumbnail Base64
                bbox_pixels = {
                    "x_min": target.bbox.x_min,
                    "y_min": target.bbox.y_min,
                    "x_max": target.bbox.x_max,
                    "y_max": target.bbox.y_max,
                }

                thumb_b64 = create_bbox_thumbnail(
                    # pyrefly: ignore [bad-argument-type]
                    image_bgr=img_bgr,
                    bbox_dict=bbox_pixels,
                    class_name=target.display_name,
                    confidence=target.calibrated_confidence,
                )

                # Physics & Shadow stretch goals
                shadow_score = round(target.shadow_evidence.shadow_score, 2)
                
                # Geometry score based on Seabed Stability & Volumetric plausibility
                stability = getattr(target.dimensions, "seabed_stability_index", 10.0)
                geometry_score = round(min(1.0, max(0.50, stability / 12.0)), 2)

                record = {
                    "id": det_id,
                    "source_image": img_path.name,
                    "cls": target.class_name,
                    "clsLabel": target.display_name,
                    "bbox_norm": [xc, yc, w, h],
                    "confidence": round(float(target.calibrated_confidence), 4),
                    "thumb": thumb_b64,
                    "shadow_score": shadow_score,
                    "geometry_score": geometry_score,
                }

                all_detections.append(record)

        except Exception as e:
            logger.error(f"Error processing {img_path.name}: {e}", exc_info=True)

    # Save outputs
    primary_out = Path(out_path)
    primary_out.parent.mkdir(parents=True, exist_ok=True)
    with open(primary_out, "w", encoding="utf-8") as f:
        json.dump(all_detections, f, indent=2)

    logger.info(f"Successfully exported {len(all_detections)} predictions to {primary_out.resolve()}")

    # Also save to outputs/synthetic_sonar_generator/real_detections.json
    generator_out = PROJECT_ROOT / "outputs" / "synthetic_sonar_generator" / "real_detections.json"
    if primary_out.resolve() != generator_out.resolve():
        generator_out.parent.mkdir(parents=True, exist_ok=True)
        with open(generator_out, "w", encoding="utf-8") as f:
            json.dump(all_detections, f, indent=2)
        logger.info(f"Saved duplicate copy to: {generator_out.resolve()}")

    return all_detections


def create_fallback_sonar_images() -> List[Path]:
    """Generate sample sonar images if no custom validation dataset is supplied."""
    out_dir = PROJECT_ROOT / "outputs" / "synthetic_sonar_generator" / "demo_dataset" / "images" / "val"
    out_dir.mkdir(parents=True, exist_ok=True)

    created = []
    sample_names = ["syn_00014_pipe.png", "syn_00021_shipwreck.png", "syn_00035_aircraft.png", "syn_00042_debris.png"]

    for name in sample_names:
        p = out_dir / name
        if not p.exists():
            # Create synthetic side-scan sonar image pattern (640x480)
            sonar_img = np.random.normal(60, 15, (480, 640)).astype(np.uint8)
            # Add nadir acoustic streak
            sonar_img[:, 310:330] = np.random.normal(20, 5, (480, 20)).astype(np.uint8)
            # Add synthetic target anomaly
            cv2.rectangle(sonar_img, (220, 180), (300, 240), 220, -1)
            # Add acoustic shadow trailing target
            cv2.rectangle(sonar_img, (300, 180), (450, 240), 10, -1)
            # Apply copper colormap
            colormapped = cv2.applyColorMap(sonar_img, cv2.COLORMAP_HOT)
            cv2.imwrite(str(p), colormapped)
        created.append(p)

    return created


def main():
    parser = argparse.ArgumentParser(description="Export YOLO Predictions in Sanshodhak Chart Schema")
    parser.add_argument("--weights", type=str, default="ml/weights/best.pt", help="Path to YOLO model weights file")
    parser.add_argument("--images", type=str, default="", help="Path to directory containing validation sonar images")
    parser.add_argument("--out", type=str, default="real_detections.json", help="Path to output JSON file")
    parser.add_argument("--confidence-threshold", type=float, default=0.20, help="Confidence cutoff")

    args = parser.parse_args()

    run_prediction_export(
        weights_path=args.weights,
        images_dir=args.images,
        out_path=args.out,
        confidence_thresh=args.confidence_threshold,
    )


if __name__ == "__main__":
    main()
