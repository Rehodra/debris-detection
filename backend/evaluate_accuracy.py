#!/usr/bin/env python3
"""
MarineScan YOLO11 Model Accuracy & Performance Evaluation Tool
=============================================================
Evaluates the 7-class YOLO11 sidescan sonar detection model.

Modes:
1. Dataset Validation (Ground Truth Evaluation):
   Computes mAP@50, mAP@50-95, Precision, Recall, and per-class metrics
   using an annotated YOLO dataset YAML.
   Usage:
     python evaluate_accuracy.py --data ../ml/configs/marine_debris.yaml --split val

2. Benchmark & Inference Evaluation (Unannotated Images/Folder):
   Evaluates inference speed, detection frequency, and confidence scores across
   one or more test images or a directory.
   Usage:
     python evaluate_accuracy.py --source ../frontend/public/accident.jpg
     python evaluate_accuracy.py --source path/to/image_folder --conf 0.25
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# 7-Class MarineScan Taxonomy
TAXONOMY_7_CLASSES = {
    0: "shipwreck",
    1: "pipe",
    2: "ghost_net",
    3: "marine_debris",
    4: "aircraft",
    5: "other",
    6: "fish",
}


def resolve_model_path() -> Path:
    """Locate yolo11_sonar_best.pt weights across standard repository locations."""
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "app" / "ml" / "weights" / "yolo11_sonar_best.pt",
        script_dir.parent / "ml" / "weights" / "yolo11_sonar_best.pt",
        script_dir / "ml" / "weights" / "yolo11_sonar_best.pt",
        script_dir / "yolo11_sonar_best.pt",
    ]
    for p in candidates:
        if p.is_file():
            return p
    raise FileNotFoundError(
        "Could not find 'yolo11_sonar_best.pt'. Checked:\n"
        + "\n".join(f"  - {c}" for c in candidates)
    )


def auto_detect_device(requested_device: str = "auto") -> str:
    """Select best compute device (mps for Mac, cuda for Windows/Linux, or cpu)."""
    if requested_device != "auto":
        return requested_device
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def run_dataset_validation(
    model: YOLO,
    data_yaml: str,
    split: str = "val",
    imgsz: int = 640,
    conf: float = 0.25,
    iou: float = 0.45,
    device: str = "cpu",
    output_json: str = "accuracy_report.json",
):
    """Run Ultralytics val() to calculate true precision, recall, and mAP metrics."""
    print("\n" + "=" * 70)
    print("  RUNNING DATASET VALIDATION (GROUND TRUTH ACCURACY METRICS)")
    print("=" * 70)
    print(f"  Dataset Config : {data_yaml}")
    print(f"  Split          : {split}")
    print(f"  Input Img Size : {imgsz}x{imgsz}")
    print(f"  Confidence Cut : {conf}")
    print(f"  IoU Threshold  : {iou}")
    print(f"  Compute Device : {device}")
    print("-" * 70)

    try:
        metrics = model.val(
            data=data_yaml,
            split=split,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            device=device,
            verbose=True,
        )
    except Exception as e:
        print(f"\n[ERROR] Validation failed: {e}")
        print("\nNote: To compute mAP/Precision/Recall on a dataset, you must provide")
        print("a dataset.yaml with annotated YOLO format ground truth labels (labels/*.txt).")
        return None

    # Extract overall metrics
    map50 = float(metrics.box.map50)
    map50_95 = float(metrics.box.map)
    mp = float(metrics.box.mp)
    mr = float(metrics.box.mr)

    print("\n" + "=" * 70)
    print("  OVERALL DETECTION ACCURACY RESULTS")
    print("=" * 70)
    print(f"  mAP@0.50       : {map50:.4f}  ({map50 * 100:.2f}%)")
    print(f"  mAP@0.50:0.95  : {map50_95:.4f}  ({map50_95 * 100:.2f}%)")
    print(f"  Mean Precision : {mp:.4f}  ({mp * 100:.2f}%)")
    print(f"  Mean Recall    : {mr:.4f}  ({mr * 100:.2f}%)")
    print("-" * 70)

    # Per-class metrics
    per_class_results = []
    print("\n  PER-CLASS ACCURACY BREAKDOWN:")
    print("  " + "-" * 66)
    print(f"  {'Class Name':<16} {'Precision':<12} {'Recall':<12} {'mAP@50':<12} {'mAP@50-95':<12}")
    print("  " + "-" * 66)

    class_names = model.names
    for i, c_idx in enumerate(metrics.box.ap_class_index):
        c_name = class_names.get(int(c_idx), f"class_{c_idx}")
        p = float(metrics.box.p[i])
        r = float(metrics.box.r[i])
        ap50 = float(metrics.box.ap50[i])
        ap = float(metrics.box.ap[i])
        print(f"  {c_name:<16} {p:<12.4f} {r:<12.4f} {ap50:<12.4f} {ap:<12.4f}")
        per_class_results.append({
            "class_id": int(c_idx),
            "class_name": c_name,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "map50": round(ap50, 4),
            "map50_95": round(ap, 4),
        })

    report = {
        "model_file": str(resolve_model_path()),
        "dataset_config": data_yaml,
        "split": split,
        "device": device,
        "metrics": {
            "map50": round(map50, 4),
            "map50_95": round(map50_95, 4),
            "mean_precision": round(mp, 4),
            "mean_recall": round(mr, 4),
        },
        "per_class": per_class_results,
        "speed": metrics.speed,
    }

    with open(output_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n[SAVED] Full accuracy report saved to: {output_json}")
    return report


def run_benchmark_evaluation(
    model: YOLO,
    source: str,
    conf: float = 0.25,
    iou: float = 0.45,
    imgsz: int = 640,
    device: str = "cpu",
    output_json: str = "benchmark_report.json",
):
    """Run detection benchmark across images or a directory (measures speed, detections, confidences)."""
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source}")

    if source_path.is_file():
        image_files = [source_path]
    else:
        valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
        image_files = sorted([p for p in source_path.iterdir() if p.suffix.lower() in valid_exts])

    if not image_files:
        raise RuntimeError(f"No valid image files found at: {source}")

    print("\n" + "=" * 70)
    print("  RUNNING MODEL BENCHMARK & INFERENCE EVALUATION")
    print("=" * 70)
    print(f"  Images Found   : {len(image_files)}")
    print(f"  Input Img Size : {imgsz}x{imgsz}")
    print(f"  Confidence Cut : {conf}")
    print(f"  IoU Threshold  : {iou}")
    print(f"  Compute Device : {device}")
    print("-" * 70)

    # Warm-up
    dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
    _ = model.predict(dummy, imgsz=imgsz, conf=conf, device=device, verbose=False)

    total_time = 0.0
    detection_counts = {c: 0 for c in TAXONOMY_7_CLASSES.values()}
    confidence_scores = {c: [] for c in TAXONOMY_7_CLASSES.values()}
    total_detections = 0
    results_per_image = []

    for img_p in image_files:
        img_bgr = cv2.imread(str(img_p))
        if img_bgr is None:
            continue

        t0 = time.perf_counter()
        preds = model.predict(
            source=img_bgr,
            conf=conf,
            iou=iou,
            imgsz=imgsz,
            device=device,
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        total_time += elapsed_ms

        boxes = preds[0].boxes
        img_dets = []
        if boxes is not None and len(boxes) > 0:
            for b in boxes:
                cls_id = int(b.cls.item())
                c_name = TAXONOMY_7_CLASSES.get(cls_id, f"unknown_{cls_id}")
                c_score = float(b.conf.item())
                xyxy = [float(v) for v in b.xyxy[0].tolist()]

                detection_counts[c_name] = detection_counts.get(c_name, 0) + 1
                confidence_scores.setdefault(c_name, []).append(c_score)
                total_detections += 1

                img_dets.append({
                    "class_id": cls_id,
                    "class_name": c_name,
                    "confidence": round(c_score, 4),
                    "bbox_xyxy": [round(v, 1) for v in xyxy],
                })

        results_per_image.append({
            "file": img_p.name,
            "latency_ms": round(elapsed_ms, 2),
            "detection_count": len(img_dets),
            "detections": img_dets,
        })

    num_images = max(1, len(results_per_image))
    avg_latency = total_time / num_images
    fps = 1000.0 / avg_latency if avg_latency > 0 else 0.0

    print("\n" + "=" * 70)
    print("  BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"  Processed Images : {num_images}")
    print(f"  Total Detections : {total_detections}")
    print(f"  Average Latency  : {avg_latency:.2f} ms/image")
    print(f"  Throughput (FPS) : {fps:.1f} frames/sec")
    print("-" * 70)

    print("\n  DETECTION & CONFIDENCE DISTRIBUTION:")
    print("  " + "-" * 55)
    print(f"  {'Class Name':<16} {'Count':<8} {'Min Conf':<10} {'Mean Conf':<10} {'Max Conf':<10}")
    print("  " + "-" * 55)
    for c_id, c_name in TAXONOMY_7_CLASSES.items():
        confs = confidence_scores.get(c_name, [])
        cnt = detection_counts.get(c_name, 0)
        if confs:
            min_c = min(confs)
            mean_c = float(np.mean(confs))
            max_c = max(confs)
            print(f"  {c_name:<16} {cnt:<8} {min_c:<10.3f} {mean_c:<10.3f} {max_c:<10.3f}")
        else:
            print(f"  {c_name:<16} {cnt:<8} {'—':<10} {'—':<10} {'—':<10}")

    benchmark_report = {
        "model_file": str(resolve_model_path()),
        "source": str(source),
        "device": device,
        "processed_images": num_images,
        "total_detections": total_detections,
        "avg_latency_ms": round(avg_latency, 2),
        "fps": round(fps, 1),
        "class_counts": detection_counts,
        "images": results_per_image,
    }

    with open(output_json, "w") as f:
        json.dump(benchmark_report, f, indent=2)
    print(f"\n[SAVED] Benchmark report saved to: {output_json}")
    return benchmark_report


def main():
    parser = argparse.ArgumentParser(
        description="MarineScan YOLO11 Model Accuracy & Performance Evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data",
        type=str,
        default=None,
        help="Path to YOLO dataset YAML (e.g. ../ml/configs/marine_debris.yaml) for ground truth mAP/Precision/Recall evaluation.",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="val",
        choices=["val", "test", "train"],
        help="Dataset split to evaluate on (default: val).",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="../frontend/public/accident.jpg",
        help="Path to an image file or directory of images for inference benchmark (default: ../frontend/public/accident.jpg).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence detection threshold (default: 0.25).",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.45,
        help="NMS IoU threshold (default: 0.45).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image resolution (default: 640).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        help="Device to use: 'auto', 'mps', 'cuda', or 'cpu' (default: auto).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="accuracy_report.json",
        help="Output path for JSON report (default: accuracy_report.json).",
    )

    args = parser.parse_args()

    model_path = resolve_model_path()
    device = auto_detect_device(args.device)

    print("=" * 70)
    print("  MARINESCAN YOLO11 ACCURACY & EVALUATION SYSTEM")
    print("=" * 70)
    print(f"  Model Weights  : {model_path}")
    print(f"  Selected Device: {device}")

    model = YOLO(str(model_path))

    # Verify 7 classes
    model_classes = model.names
    print(f"  Model Classes  : {len(model_classes)} classes detected")
    for cid in range(7):
        expected = TAXONOMY_7_CLASSES[cid]
        actual = model_classes.get(cid, "MISSING")
        status = "MATCH" if expected == actual else f"MISMATCH (expected {expected}, got {actual})"
        print(f"    Class {cid}: {actual:<16} [{status}]")

    # If dataset YAML provided, run full dataset validation (mAP50, mAP50-95, P, R)
    if args.data:
        run_dataset_validation(
            model=model,
            data_yaml=args.data,
            split=args.split,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=device,
            output_json=args.output,
        )
    else:
        # Otherwise run image / directory benchmark
        run_benchmark_evaluation(
            model=model,
            source=args.source,
            conf=args.conf,
            iou=args.iou,
            imgsz=args.imgsz,
            device=device,
            output_json=args.output,
        )


if __name__ == "__main__":
    main()
