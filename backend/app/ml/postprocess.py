"""
Post-processing utilities for MarineScan Debris Detection results.
Converts Ultralytics YOLO Results into structured bounding box objects,
calculates spatial metrics, and renders styled visual overlays.
"""

import io
import uuid
import base64
from typing import List, Dict, Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from app.ml.class_map import get_class_metadata, get_class_name




def parse_yolo_results(
    results,
    min_confidence: float = 0.0,
    classes_filter: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Parse an Ultralytics Results object into structured detections list and summary statistics.

    Args:
        results: Ultralytics Results object (or list of 1 result)
        min_confidence: Minimum confidence cutoff
        classes_filter: Optional list of class names to keep (e.g. ['shipwreck', 'aircraft'])

    Returns:
        Tuple of (detections_list, summary_dict)
    """
    if isinstance(results, (list, tuple)):
        result = results[0]
    else:
        result = results

    orig_h, orig_w = result.orig_shape if hasattr(result, "orig_shape") else (640, 640)
    boxes = result.boxes

    detections: List[Dict[str, Any]] = []
    class_counts: Dict[str, int] = {}
    max_confidence: float = 0.0
    critical_detected: bool = False

    if boxes is not None and len(boxes) > 0:
        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy()
        clss = boxes.cls.cpu().numpy()

        for idx in range(len(confs)):
            conf = float(confs[idx])
            if conf < min_confidence:
                continue

            class_id = int(clss[idx])
            model_names = getattr(result, "names", None) or {}
            class_name = model_names.get(class_id, get_class_name(class_id))

            if classes_filter and class_name.lower() not in [c.lower() for c in classes_filter]:
                continue

            metadata = get_class_metadata(class_name)
            risk_level = metadata.risk_level if metadata else "Unknown"
            category = metadata.category if metadata else "Unknown"
            color_hex = metadata.color_hex if metadata else "#3B82F6"
            color_rgb = metadata.color_rgb if metadata else (59, 130, 246)

            x_min = max(0.0, float(xyxy[idx][0]))
            y_min = max(0.0, float(xyxy[idx][1]))
            x_max = min(float(orig_w), float(xyxy[idx][2]))
            y_max = min(float(orig_h), float(xyxy[idx][3]))
            width = max(0.0, x_max - x_min)
            height = max(0.0, y_max - y_min)
            area_pixels = width * height

            # Normalized bounding box [0.0 - 1.0]
            norm_x_min = x_min / orig_w if orig_w > 0 else 0.0
            norm_y_min = y_min / orig_h if orig_h > 0 else 0.0
            norm_x_max = x_max / orig_w if orig_w > 0 else 0.0
            norm_y_max = y_max / orig_h if orig_h > 0 else 0.0

            if risk_level in ["Critical", "High"]:
                critical_detected = True

            max_confidence = max(max_confidence, conf)
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

            detection_id = f"det_{uuid.uuid4().hex[:8]}"

            detections.append({
                "detection_id": detection_id,
                "class_id": class_id,
                "class_name": class_name,
                "display_name": metadata.display_name if metadata else class_name,
                "category": category,
                "risk_level": risk_level,
                "confidence": round(conf, 4),
                "bbox": {
                    "x_min": round(x_min, 2),
                    "y_min": round(y_min, 2),
                    "x_max": round(x_max, 2),
                    "y_max": round(y_max, 2),
                    "width": round(width, 2),
                    "height": round(height, 2),
                    "normalized_x_min": round(norm_x_min, 4),
                    "normalized_y_min": round(norm_y_min, 4),
                    "normalized_x_max": round(norm_x_max, 4),
                    "normalized_y_max": round(norm_y_max, 4),
                },
                "area_pixels": round(area_pixels, 2),
                "color_hex": color_hex,
                "color_rgb": list(color_rgb),
            })

    # Sort detections by confidence descending
    detections.sort(key=lambda x: x["confidence"], reverse=True)

    summary = {
        "total_detections": len(detections),
        "class_counts": class_counts,
        "max_confidence": round(max_confidence, 4) if detections else 0.0,
        "critical_detected": critical_detected,
    }

    return detections, summary


def render_detections_overlay(
    image_bgr: np.ndarray,
    detections: List[Dict[str, Any]],
    line_thickness: int = 2,
    font_scale: float = 0.55,
) -> np.ndarray:
    """
    Render professional bounding boxes and labels onto the BGR image.
    Uses tailored colors, semi-transparent label tags, and high-visibility text.
    """
    annotated = image_bgr.copy()
    overlay = annotated.copy()

    for det in detections:
        bbox = det["bbox"]
        x1, y1 = int(bbox["x_min"]), int(bbox["y_min"])
        x2, y2 = int(bbox["x_max"]), int(bbox["y_max"])
        
        # Color from RGB -> BGR for OpenCV
        rgb = det.get("color_rgb", [59, 130, 246])
        bgr_color = (int(rgb[2]), int(rgb[1]), int(rgb[0]))

        # Draw semi-transparent bounding box outline
        cv2.rectangle(annotated, (x1, y1), (x2, y2), bgr_color, line_thickness)

        # Label content
        label = f"{det['display_name']} {int(det['confidence'] * 100)}%"
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1
        )

        # Draw badge background
        tag_y1 = max(0, y1 - text_h - 8)
        tag_y2 = y1
        tag_x1 = x1
        tag_x2 = min(annotated.shape[1], x1 + text_w + 10)

        cv2.rectangle(overlay, (tag_x1, tag_y1), (tag_x2, tag_y2), bgr_color, -1)

    # Blend overlay with annotated image for semi-transparent badges
    alpha = 0.85
    cv2.addWeighted(overlay, alpha, annotated, 1 - alpha, 0, annotated)

    # Draw sharp white text on top of blended badges
    for det in detections:
        bbox = det["bbox"]
        x1, y1 = int(bbox["x_min"]), int(bbox["y_min"])
        label = f"{det['display_name']} {int(det['confidence'] * 100)}%"
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1
        )
        tag_y1 = max(0, y1 - text_h - 8)
        text_pos = (x1 + 5, tag_y1 + text_h + 3)
        cv2.putText(
            annotated,
            label,
            text_pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    return annotated


def encode_image_to_jpeg_bytes(image_bgr: np.ndarray, quality: int = 90) -> bytes:
    """Encode OpenCV BGR image into JPEG bytes."""
    success, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise ValueError("Failed to encode image to JPEG.")
    return encoded.tobytes()


def encode_image_to_base64(image_bgr: np.ndarray, quality: int = 90) -> str:
    """Encode OpenCV BGR image into base64 data URI string."""
    jpeg_bytes = encode_image_to_jpeg_bytes(image_bgr, quality=quality)
    b64_str = base64.b64encode(jpeg_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64_str}"
