"""
Advanced Inference Service for MarineScan Debris Detection.
Orchestrates image decoding, pre-inference acoustic enhancement,
standard and high-resolution tiled / sliding-window YOLO inference,
global NMS merging, physical metric estimation, and visualization rendering.
"""

import io
import time
import uuid
import logging
from typing import Optional, List, Tuple, Dict, Any

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.ml.model_loader import model_loader
from app.ml.class_map import get_class_metadata, get_class_name
from app.ml.postprocess import (
    parse_yolo_results,
    render_detections_overlay,
    encode_image_to_jpeg_bytes,
    encode_image_to_base64,
)
from app.schemas.detection import (
    DetectionResponse,
    DetectionItem,
    DetectionSummary,
    BoundingBox,
    PhysicalDimensions,
    ImageMetadata,
    TimingBreakdown,
    TilingConfig,
    BatchDetectionResponse,
)
from app.schemas.preprocessing import PreprocessingConfig, PreprocessingPreset
from app.services.preprocessing_service import preprocessing_service

logger = logging.getLogger("marinescan.services.inference")


class InferenceService:
    """Production inference engine for sonar and marine optical debris detection."""

    def __init__(self) -> None:
        self.loader = model_loader

    # -------------------------------------------------------------------------
    # Decoding & Input Formatting
    # -------------------------------------------------------------------------

    def decode_image_bytes(self, image_bytes: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """
        Decode raw image bytes into an OpenCV BGR numpy array and extract metadata.
        """
        if not image_bytes:
            raise ValueError("Empty image data received.")

        img_format = None
        try:
            with Image.open(io.BytesIO(image_bytes)) as pil_img:
                img_format = pil_img.format
        except Exception:
            pass

        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_bgr is None or img_bgr.size == 0:
            raise ValueError("Could not decode image from provided data. Supported formats: JPEG, PNG, WEBP, BMP, TIFF.")

        h, w, c = img_bgr.shape
        metadata = ImageMetadata(
            width=w,
            height=h,
            channels=c,
            format=img_format or "JPEG",
        )
        return img_bgr, metadata

    # -------------------------------------------------------------------------
    # Physical Dimension Estimation
    # -------------------------------------------------------------------------

    def attach_physical_dimensions(
        self,
        detections: List[Dict[str, Any]],
        meters_per_pixel: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Calculate real-world length, width, and seabed footprint area
        using Ground Sampling Distance (GSD).
        """
        if meters_per_pixel is None or meters_per_pixel <= 0.0:
            return detections

        for det in detections:
            bbox = det["bbox"]
            w_px = bbox["width"]
            h_px = bbox["height"]

            length_m = round(max(w_px, h_px) * meters_per_pixel, 2)
            width_m = round(min(w_px, h_px) * meters_per_pixel, 2)
            area_sq_m = round(length_m * width_m, 2)

            det["physical_dimensions"] = {
                "length_meters": length_m,
                "width_meters": width_m,
                "area_sq_meters": area_sq_m,
                "meters_per_pixel": meters_per_pixel,
            }

        return detections

    # -------------------------------------------------------------------------
    # Core Array-based Inference
    # -------------------------------------------------------------------------

    def predict_array(
        self,
        image_bgr: np.ndarray,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = 0.45,
        return_visualization: bool = False,
        classes_filter: Optional[List[str]] = None,
        preprocessing_preset: Optional[str] = None,
        meters_per_pixel: Optional[float] = None,
        use_tiling: bool = False,
        tiling_config: Optional[TilingConfig] = None,
        format_name: str = "RAW",
        decode_duration_ms: float = 0.0,
    ) -> DetectionResponse:
        """
        Run inference directly on a NumPy BGR image array.
        Supports optional preprocessing, high-res tiling, and physical metric estimations.
        """
        total_start = time.perf_counter()
        img_h, img_w = image_bgr.shape[:2]
        img_meta = ImageMetadata(width=img_w, height=img_h, channels=3, format=format_name)

        processed_img = image_bgr.copy()
        prep_start = time.perf_counter()
        if preprocessing_preset:
            try:
                preset_enum = PreprocessingPreset(preprocessing_preset.lower())
                cfg = PreprocessingConfig(preset=preset_enum)
                processed_img, _ = preprocessing_service.process_image(processed_img, config=cfg)
            except Exception as pe:
                logger.warning("Preprocessing preset %s failed (%s), proceeding with original.", preprocessing_preset, pe)
        prep_duration_ms = (time.perf_counter() - prep_start) * 1000.0

        conf = confidence_threshold if confidence_threshold is not None else settings.CONFIDENCE_THRESHOLD
        iou = iou_threshold if iou_threshold is not None else 0.45

        # Check if sliding-window tiling is requested or automatically beneficial
        if use_tiling:
            detections, summary, infer_duration_ms, post_duration_ms = self.predict_tiled(
                image_bgr=processed_img,
                confidence_threshold=conf,
                iou_threshold=iou,
                classes_filter=classes_filter,
                tiling_config=tiling_config or TilingConfig(),
            )
            tiling_applied = True
        else:
            tiling_applied = False
            model = self.loader.get_model()

            infer_start = time.perf_counter()
            results = model.predict(
                source=processed_img,
                conf=conf,
                iou=iou,
                device=self.loader.device,
                verbose=False,
            )
            infer_duration_ms = (time.perf_counter() - infer_start) * 1000.0

            post_start = time.perf_counter()
            detections, summary = parse_yolo_results(
                results=results,
                min_confidence=conf,
                classes_filter=classes_filter,
            )
            post_duration_ms = (time.perf_counter() - post_start) * 1000.0

        # Attach real-world metric estimations if resolution is provided
        if meters_per_pixel:
            detections = self.attach_physical_dimensions(detections, meters_per_pixel=meters_per_pixel)

        # Render overlay if requested
        annotated_b64 = None
        if return_visualization:
            annotated_bgr = render_detections_overlay(image_bgr, detections)
            annotated_b64 = encode_image_to_base64(annotated_bgr)

        total_duration_ms = (time.perf_counter() - total_start) * 1000.0 + decode_duration_ms

        timing = TimingBreakdown(
            decode_time_ms=round(decode_duration_ms, 2),
            preprocessing_time_ms=round(prep_duration_ms, 2),
            inference_time_ms=round(infer_duration_ms, 2),
            postprocess_time_ms=round(post_duration_ms, 2),
            total_time_ms=round(total_duration_ms, 2),
        )

        return DetectionResponse(
            status="success",
            model_name="MarineScan YOLOv8 Debris Detector",
            device=self.loader.device,
            inference_time_ms=round(infer_duration_ms, 2),
            total_time_ms=round(total_duration_ms, 2),
            timing_breakdown=timing,
            image_info=img_meta,
            detections=detections,
            summary=summary,
            tiling_applied=tiling_applied,
            annotated_image_base64=annotated_b64,
        )

    # -------------------------------------------------------------------------
    # High-Resolution Tiled / Sliding Window Inference
    # -------------------------------------------------------------------------

    def predict_tiled(
        self,
        image_bgr: np.ndarray,
        confidence_threshold: float,
        iou_threshold: float,
        classes_filter: Optional[List[str]] = None,
        tiling_config: Optional[TilingConfig] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], float, float]:
        """
        Slice high-resolution sonar waterfall into overlapping tiles, run batched inference,
        translate tile coordinates to global space, and perform global NMS.
        """
        cfg = tiling_config or TilingConfig()
        img_h, img_w = image_bgr.shape[:2]
        tile_size = cfg.tile_size
        step = max(1, int(tile_size * (1.0 - cfg.overlap_ratio)))

        # Generate slice coordinates
        x_starts = list(range(0, max(1, img_w - tile_size + 1), step))
        if len(x_starts) == 0 or x_starts[-1] + tile_size < img_w:
            x_starts.append(max(0, img_w - tile_size))
        x_starts = sorted(list(set(x_starts)))

        y_starts = list(range(0, max(1, img_h - tile_size + 1), step))
        if len(y_starts) == 0 or y_starts[-1] + tile_size < img_h:
            y_starts.append(max(0, img_h - tile_size))
        y_starts = sorted(list(set(y_starts)))

        tiles: List[np.ndarray] = []
        offsets: List[Tuple[int, int]] = []

        for y in y_starts:
            for x in x_starts:
                tile = image_bgr[y : y + tile_size, x : x + tile_size]
                # Pad if tile is smaller than expected tile_size
                th, tw = tile.shape[:2]
                if th < tile_size or tw < tile_size:
                    padded_tile = np.zeros((tile_size, tile_size, 3), dtype=np.uint8)
                    padded_tile[:th, :tw] = tile
                    tile = padded_tile

                tiles.append(tile)
                offsets.append((x, y))

        model = self.loader.get_model()

        # Run batched inference across all tiles
        infer_start = time.perf_counter()
        batch_results = model.predict(
            source=tiles,
            conf=confidence_threshold,
            iou=iou_threshold,
            device=self.loader.device,
            verbose=False,
        )
        infer_duration_ms = (time.perf_counter() - infer_start) * 1000.0

        post_start = time.perf_counter()
        raw_boxes = []
        raw_scores = []
        raw_class_ids = []

        for idx, (res, (ox, oy)) in enumerate(zip(batch_results, offsets)):
            if res.boxes is None or len(res.boxes) == 0:
                continue

            xyxy = res.boxes.xyxy.cpu().numpy()
            confs = res.boxes.conf.cpu().numpy()
            clss = res.boxes.cls.cpu().numpy()

            for b_idx in range(len(confs)):
                conf = float(confs[b_idx])
                cid = int(clss[b_idx])
                cname = get_class_name(cid)

                if classes_filter and cname.lower() not in [c.lower() for c in classes_filter]:
                    continue

                gx1 = float(xyxy[b_idx][0] + ox)
                gy1 = float(xyxy[b_idx][1] + oy)
                gx2 = float(xyxy[b_idx][2] + ox)
                gy2 = float(xyxy[b_idx][3] + oy)

                # Clamp to global image boundary
                gx1 = max(0.0, min(float(img_w), gx1))
                gy1 = max(0.0, min(float(img_h), gy1))
                gx2 = max(0.0, min(float(img_w), gx2))
                gy2 = max(0.0, min(float(img_h), gy2))

                w = max(0.0, gx2 - gx1)
                h = max(0.0, gy2 - gy1)

                if w > 2 and h > 2:
                    raw_boxes.append([int(gx1), int(gy1), int(w), int(h)])
                    raw_scores.append(conf)
                    raw_class_ids.append(cid)

        # Global NMS across tiles
        final_detections: List[Dict[str, Any]] = []
        class_counts: Dict[str, int] = {}
        max_confidence: float = 0.0
        critical_detected: bool = False

        if len(raw_boxes) > 0:
            indices = cv2.dnn.NMSBoxes(
                bboxes=raw_boxes,
                scores=raw_scores,
                score_threshold=confidence_threshold,
                nms_threshold=cfg.iou_merge_threshold,
            )

            if len(indices) > 0:
                for i in indices.flatten():
                    bx, by, bw, bh = raw_boxes[i]
                    conf = raw_scores[i]
                    cid = raw_class_ids[i]
                    cname = get_class_name(cid)
                    meta = get_class_metadata(cid)

                    risk_level = meta.risk_level if meta else "Unknown"
                    if risk_level in ["Critical", "High"]:
                        critical_detected = True

                    max_confidence = max(max_confidence, conf)
                    class_counts[cname] = class_counts.get(cname, 0) + 1

                    final_detections.append({
                        "detection_id": f"det_{uuid.uuid4().hex[:8]}",
                        "class_id": cid,
                        "class_name": cname,
                        "display_name": meta.display_name if meta else cname,
                        "category": meta.category if meta else "Unknown",
                        "risk_level": risk_level,
                        "confidence": round(float(conf), 4),
                        "bbox": {
                            "x_min": float(bx),
                            "y_min": float(by),
                            "x_max": float(bx + bw),
                            "y_max": float(by + bh),
                            "width": float(bw),
                            "height": float(bh),
                            "normalized_x_min": round(bx / img_w, 4),
                            "normalized_y_min": round(by / img_h, 4),
                            "normalized_x_max": round((bx + bw) / img_w, 4),
                            "normalized_y_max": round((by + bh) / img_h, 4),
                        },
                        "area_pixels": float(bw * bh),
                        "color_hex": meta.color_hex if meta else "#3B82F6",
                        "color_rgb": list(meta.color_rgb) if meta else [59, 130, 246],
                    })

        final_detections.sort(key=lambda d: d["confidence"], reverse=True)
        post_duration_ms = (time.perf_counter() - post_start) * 1000.0

        summary = {
            "total_detections": len(final_detections),
            "class_counts": class_counts,
            "max_confidence": round(max_confidence, 4) if final_detections else 0.0,
            "critical_detected": critical_detected,
        }

        return final_detections, summary, infer_duration_ms, post_duration_ms

    # -------------------------------------------------------------------------
    # High-Level Interfaces (Bytes, Batch, Render)
    # -------------------------------------------------------------------------

    def predict(
        self,
        image_bytes: bytes,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = 0.45,
        return_visualization: bool = False,
        classes_filter: Optional[List[str]] = None,
        preprocessing_preset: Optional[str] = None,
        meters_per_pixel: Optional[float] = None,
        use_tiling: bool = False,
        tiling_config: Optional[TilingConfig] = None,
    ) -> DetectionResponse:
        """
        Execute detection on raw image bytes.
        """
        decode_start = time.perf_counter()
        img_bgr, img_meta = self.decode_image_bytes(image_bytes)
        decode_duration_ms = (time.perf_counter() - decode_start) * 1000.0

        return self.predict_array(
            image_bgr=img_bgr,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            return_visualization=return_visualization,
            classes_filter=classes_filter,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
            use_tiling=use_tiling,
            tiling_config=tiling_config,
            format_name=img_meta.format or "JPEG",
            decode_duration_ms=decode_duration_ms,
        )

    def predict_batch(
        self,
        image_bytes_list: List[bytes],
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = 0.45,
        return_visualization: bool = False,
        classes_filter: Optional[List[str]] = None,
        preprocessing_preset: Optional[str] = None,
        meters_per_pixel: Optional[float] = None,
    ) -> BatchDetectionResponse:
        """
        Execute parallel batched detection across multiple images.
        """
        batch_start = time.perf_counter()
        if not image_bytes_list:
            raise ValueError("Empty image batch provided.")

        results: List[DetectionResponse] = []
        total_detections = 0

        for img_bytes in image_bytes_list:
            resp = self.predict(
                image_bytes=img_bytes,
                confidence_threshold=confidence_threshold,
                iou_threshold=iou_threshold,
                return_visualization=return_visualization,
                classes_filter=classes_filter,
                preprocessing_preset=preprocessing_preset,
                meters_per_pixel=meters_per_pixel,
            )
            results.append(resp)
            total_detections += resp.summary.total_detections

        batch_duration_ms = (time.perf_counter() - batch_start) * 1000.0

        return BatchDetectionResponse(
            status="success",
            total_images=len(image_bytes_list),
            total_detections=total_detections,
            batch_duration_ms=round(batch_duration_ms, 2),
            results=results,
        )

    def predict_and_render_image(
        self,
        image_bytes: bytes,
        confidence_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = 0.45,
        preprocessing_preset: Optional[str] = None,
        use_tiling: bool = False,
        meters_per_pixel: Optional[float] = None,
    ) -> Tuple[bytes, int]:
        """
        Run inference and return directly the annotated JPEG bytes and count.
        """
        resp = self.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            return_visualization=False,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
            use_tiling=use_tiling,
        )

        img_bgr, _ = self.decode_image_bytes(image_bytes)
        # Convert Pydantic DetectionItems to dict for renderer
        det_dicts = [d.model_dump() for d in resp.detections]
        annotated_bgr = render_detections_overlay(img_bgr, det_dicts)
        jpeg_bytes = encode_image_to_jpeg_bytes(annotated_bgr)

        return jpeg_bytes, resp.summary.total_detections


# Global service instance
inference_service = InferenceService()
