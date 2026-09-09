#!/usr/bin/env python3
"""
Independent Model-Only Validation Script for MarineScan YOLO11 Debris Detector.

Performs ONLY:
  Image -> YOLO11 Direct Inference -> Detections -> Annotated Image + JSON Report

Does NOT execute:
  - Preprocessing service
  - Shadow analysis
  - Physics validation
  - Confidence fusion
  - Geolocation
  - Risk assessment
  - Master pipeline
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

# Ensure backend directory is on sys.path for relative resolution
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Try importing Ultralytics YOLO
try:
    from ultralytics import YOLO
except ImportError:
    print("\n[ERROR] 'ultralytics' library is not installed in the active environment.")
    print("Please run using the project virtual environment:")
    print("  ./venv/bin/python test_yolo11_model.py <image_path>\n")
    sys.exit(1)

# Expected 7-class MarineScan taxonomy
EXPECTED_CLASSES: Dict[int, str] = {
    0: "shipwreck",
    1: "pipe",
    2: "ghost_net",
    3: "marine_debris",
    4: "aircraft",
    5: "other",
    6: "fish",
}

# Color palette for annotation (BGR format for OpenCV)
CLASS_COLORS: Dict[str, Tuple[int, int, int]] = {
    "shipwreck": (70, 57, 230),       # Red
    "pipe": (97, 162, 244),           # Orange
    "ghost_net": (81, 111, 231),       # Coral / Brick
    "marine_debris": (106, 196, 233),  # Gold / Yellow
    "aircraft": (40, 40, 214),         # Crimson
    "other": (157, 123, 69),           # Slate Blue
    "fish": (143, 157, 42),            # Teal Green
}
DEFAULT_COLOR: Tuple[int, int, int] = (200, 200, 200)


def locate_model_weights(custom_path: Optional[str] = None) -> Path:
    """Locate the exact yolo11_sonar_best.pt model weights file."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_file():
            return p
        print(f"\n[ERROR] Specified weights file does not exist: {custom_path}")
        sys.exit(1)

    search_candidates = [
        BACKEND_DIR / "app" / "ml" / "weights" / "yolo11_sonar_best.pt",
        REPO_ROOT / "ml" / "weights" / "yolo11_sonar_best.pt",
        REPO_ROOT / "backend" / "app" / "ml" / "weights" / "yolo11_sonar_best.pt",
        Path.cwd() / "app" / "ml" / "weights" / "yolo11_sonar_best.pt",
        Path.cwd() / "ml" / "weights" / "yolo11_sonar_best.pt",
        BACKEND_DIR / "app" / "ml" / "weights" / "best.pt",
        REPO_ROOT / "ml" / "weights" / "best.pt",
    ]

    for cand in search_candidates:
        if cand.is_file():
            return cand.resolve()

    # Search for any .pt file in known weights directories
    fallback_dirs = [
        BACKEND_DIR / "app" / "ml" / "weights",
        REPO_ROOT / "ml" / "weights",
    ]
    for d in fallback_dirs:
        if d.is_dir():
            pt_files = list(d.glob("*.pt"))
            if pt_files:
                return pt_files[0].resolve()

    print("\n[ERROR] Model weights file could not be located in standard project paths:")
    for cand in search_candidates[:4]:
        print(f"  - {cand}")
    print("\nPlease verify weights exist or provide path via --weights <path>")
    sys.exit(1)


def verify_classes(actual_names: Dict[int, str]) -> Tuple[bool, str]:
    """Verify if actual model classes match the required 7-class taxonomy."""
    # Convert keys to int if necessary
    int_names = {int(k): str(v) for k, v in actual_names.items()}

    mismatches = []
    if len(int_names) != len(EXPECTED_CLASSES):
        mismatches.append(f"Total class count mismatch: expected {len(EXPECTED_CLASSES)}, got {len(int_names)}")

    for cid, cname in EXPECTED_CLASSES.items():
        if cid not in int_names:
            mismatches.append(f"Missing class ID {cid} ('{cname}') in model.")
        elif int_names[cid].lower() != cname.lower():
            mismatches.append(f"Class ID {cid} mismatch: expected '{cname}', got '{int_names[cid]}'")

    for cid, cname in int_names.items():
        if cid not in EXPECTED_CLASSES:
            mismatches.append(f"Unexpected extra class in model: ID {cid} ('{cname}')")

    if mismatches:
        detail = "\n".join(f"  * {m}" for m in mismatches)
        return False, detail

    return True, "All 7 classes and IDs exactly match the MarineScan specification."


def validate_and_load_image(image_path: str) -> Tuple[np.ndarray, Path]:
    """Validate image existence, format, and load via OpenCV."""
    p = Path(image_path).resolve()
    if not p.exists():
        print(f"\n[ERROR] Input image file not found: {image_path}")
        sys.exit(1)

    if not p.is_file():
        print(f"\n[ERROR] Path is not a file: {image_path}")
        sys.exit(1)

    valid_extensions = {".jpg", ".jpeg", ".png"}
    if p.suffix.lower() not in valid_extensions:
        print(f"\n[ERROR] Unsupported image extension '{p.suffix}'. Supported: JPG, JPEG, PNG")
        sys.exit(1)

    img = cv2.imread(str(p))
    if img is None or img.size == 0:
        print(f"\n[ERROR] Failed to decode image from file: {image_path}. File may be corrupted.")
        sys.exit(1)

    return img, p


def draw_annotations(
    img_bgr: np.ndarray,
    detections: List[Dict[str, Any]]
) -> np.ndarray:
    """Render bounding boxes, class labels, and confidence tags on canvas."""
    annotated = img_bgr.copy()
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.55
    font_thickness = 1

    for det in detections:
        cname = det["class_name"]
        conf = det["confidence"]
        x_min, y_min, x_max, y_max = [int(v) for v in det["bbox"]]

        color = CLASS_COLORS.get(cname.lower(), DEFAULT_COLOR)

        # Draw main bounding box
        cv2.rectangle(annotated, (x_min, y_min), (x_max, y_max), color, 2)

        # Label text
        label = f"{cname} {conf * 100:.1f}%"
        (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)

        # Background badge above or inside box
        label_ymin = max(0, y_min - text_h - baseline - 4)
        label_ymax = label_ymin + text_h + baseline + 4
        label_xmax = min(annotated.shape[1], x_min + text_w + 8)

        cv2.rectangle(
            annotated,
            (x_min, label_ymin),
            (label_xmax, label_ymax),
            color,
            -1
        )

        # Text inside badge
        text_baseline_y = label_ymax - baseline - 2
        cv2.putText(
            annotated,
            label,
            (x_min + 4, text_baseline_y),
            font,
            font_scale,
            (255, 255, 255),
            font_thickness,
            cv2.LINE_AA,
        )

    return annotated


def run_validation(
    image_path: str,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    imgsz: int = 640,
    weights_path: Optional[str] = None,
    output_img_path: str = "yolo11_validation_result.jpg",
    output_json_path: str = "yolo11_validation_result.json",
) -> None:
    """Execute model-only inference validation on target image."""
    print("\n" + "=" * 65)
    print("  MarineScan YOLO11 Model-Only Independent Validation")
    print("=" * 65)

    # 1. Locate weights
    weights_file = locate_model_weights(weights_path)
    print(f"\n[1] Model Weights Located:")
    print(f"    Path:      {weights_file}")
    print(f"    Size:      {weights_file.stat().st_size / (1024 * 1024):.2f} MB")

    # 2. Load model
    print(f"\n[2] Loading Ultralytics Model...")
    try:
        model = YOLO(str(weights_file))
    except Exception as e:
        print(f"\n[ERROR] Model loading failed: {e}")
        sys.exit(1)

    model_task = getattr(model, "task", "detect")
    model_type = type(model.model).__name__ if hasattr(model, "model") else "YOLO11"
    raw_names = getattr(model, "names", {})
    actual_classes = {int(k): str(v) for k, v in raw_names.items()}

    print(f"    Model Task:    {model_task}")
    print(f"    Model Type:    {model_type}")
    print(f"    Class Count:   {len(actual_classes)}")
    print(f"    Model Classes:")
    for cid, cname in sorted(actual_classes.items()):
        print(f"      [{cid}] {cname}")

    # 3. Verify classes
    print(f"\n[3] Verifying 7-Class Marine Taxonomy...")
    classes_ok, class_msg = verify_classes(actual_classes)
    if classes_ok:
        print(f"    STATUS: [PASSED]")
        print(f"    {class_msg}")
    else:
        print(f"    STATUS: [FAILED / MISMATCH]")
        print(f"{class_msg}")

    # 4. Load Image
    print(f"\n[4] Loading and Validating Input Image:")
    img_bgr, resolved_img_path = validate_and_load_image(image_path)
    img_h, img_w, img_c = img_bgr.shape
    print(f"    Path:          {resolved_img_path}")
    print(f"    Dimensions:    {img_w} × {img_h} px ({img_c} channels)")

    # 5. Run Inference
    print(f"\n[5] Executing Model Inference:")
    print(f"    Confidence:    {conf_threshold}")
    print(f"    IoU Threshold: {iou_threshold}")
    print(f"    Inference Size:{imgsz} px")

    try:
        t0 = time.perf_counter()
        results = model.predict(
            source=img_bgr,
            conf=conf_threshold,
            iou=iou_threshold,
            imgsz=imgsz,
            verbose=False,
        )
        infer_duration_ms = (time.perf_counter() - t0) * 1000.0
    except Exception as e:
        print(f"\n[ERROR] Inference execution failed: {e}")
        sys.exit(1)

    # 6. Parse Detections
    result = results[0]
    boxes = result.boxes
    detections: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {cname: 0 for cname in EXPECTED_CLASSES.values()}

    if boxes is not None and len(boxes) > 0:
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy()

        for idx in range(len(confs)):
            cid = int(clss[idx])
            cname = actual_classes.get(cid, f"class_{cid}")
            conf = float(confs[idx])

            x1 = round(float(xyxy[idx][0]), 2)
            y1 = round(float(xyxy[idx][1]), 2)
            x2 = round(float(xyxy[idx][2]), 2)
            y2 = round(float(xyxy[idx][3]), 2)

            bw = round(max(0.0, x2 - x1), 2)
            bh = round(max(0.0, y2 - y1), 2)

            class_counts[cname] = class_counts.get(cname, 0) + 1

            detections.append({
                "detection_index": idx + 1,
                "class_id": cid,
                "class_name": cname,
                "confidence": round(conf, 4),
                "bbox": [x1, y1, x2, y2],
                "bbox_width": bw,
                "bbox_height": bh,
            })

    print(f"    Inference Time:{infer_duration_ms:.2f} ms")
    print(f"    Detections:    {len(detections)}")

    # 7. Print Detections Detail
    print(f"\n[6] Detections Found ({len(detections)} total):")
    if not detections:
        print("    No objects detected above confidence threshold.")
    else:
        for d in detections:
            print(f"    Detection #{d['detection_index']}")
            print(f"      Class:        {d['class_name']} (ID: {d['class_id']})")
            print(f"      Confidence:   {d['confidence'] * 100:.2f}%")
            print(f"      Bounding box: [{d['bbox'][0]}, {d['bbox'][1]}, {d['bbox'][2]}, {d['bbox'][3]}]")
            print(f"      Width:        {d['bbox_width']} px")
            print(f"      Height:       {d['bbox_height']} px")

    # 8. Print Class Summary
    print(f"\n[7] Class summary:")
    for cname in sorted(EXPECTED_CLASSES.values()):
        count = class_counts.get(cname, 0)
        print(f"    {cname}: {count}")

    # 9. Generate Annotated JPEG Image
    annotated_img = draw_annotations(img_bgr, detections)
    out_img_path = Path(output_img_path).resolve()
    cv2.imwrite(str(out_img_path), annotated_img)
    print(f"\n[8] Annotated Image Saved:")
    print(f"    {out_img_path}")

    # 10. Generate JSON Report
    report = {
        "model_path": str(weights_file),
        "model_task": model_task,
        "model_type": model_type,
        "model_classes": actual_classes,
        "class_verification": {
            "passed": classes_ok,
            "details": class_msg,
            "expected_classes": EXPECTED_CLASSES,
            "actual_classes": actual_classes,
        },
        "input_image": str(resolved_img_path),
        "image_width": img_w,
        "image_height": img_h,
        "inference_parameters": {
            "confidence_threshold": conf_threshold,
            "iou_threshold": iou_threshold,
            "imgsz": imgsz,
        },
        "inference_time_ms": round(infer_duration_ms, 2),
        "detection_count": len(detections),
        "class_summary": class_counts,
        "detections": detections,
    }

    out_json_path = Path(output_json_path).resolve()
    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[9] JSON Report Saved:")
    print(f"    {out_json_path}")

    print("\n" + "=" * 65)
    print("  Validation Execution Finished Successfully")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Independent Model-Only Validation Script for MarineScan YOLO11 Debris Detector."
    )
    parser.add_argument(
        "image_path",
        type=str,
        help="Path to sidescan sonar image (JPG, JPEG, PNG)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence cutoff threshold (default: 0.25)",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.45,
        help="Non-maximum suppression IoU threshold (default: 0.45)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size (default: 640)",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Optional custom weights file path override",
    )
    parser.add_argument(
        "--output-img",
        type=str,
        default="yolo11_validation_result.jpg",
        help="Output path for annotated image (default: yolo11_validation_result.jpg)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="yolo11_validation_result.json",
        help="Output path for JSON report (default: yolo11_validation_result.json)",
    )

    args = parser.parse_args()

    run_validation(
        image_path=args.image_path,
        conf_threshold=args.conf,
        iou_threshold=args.iou,
        imgsz=args.imgsz,
        weights_path=args.weights,
        output_img_path=args.output_img,
        output_json_path=args.output_json,
    )


if __name__ == "__main__":
    main()
