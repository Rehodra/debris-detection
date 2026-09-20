"""
Shadow Service for Sonar and Marine Debris Analytics.
Extracts acoustic shadow candidates, determines spatial vectors,
evaluates directional alignment with sonar acoustics, calculates physical extent,
and computes composite shadow confidence scores.
"""

import math
import uuid
import logging
from typing import Optional, List, Tuple, Dict, Any

import cv2
import numpy as np

from app.schemas.detection import BoundingBox, DetectionItem
from app.schemas.shadow import (
    ShadowCandidate,
    SpatialRelationship,
    ShadowDirection,
    ShadowExtent,
    ShadowAnalysisResult,
    ShadowAnalysisResponse,
)
from app.ml.postprocess import encode_image_to_jpeg_bytes, encode_image_to_base64

logger = logging.getLogger("marinescan.services.shadow")


class ShadowService:
    """Production service for acoustic shadow extraction and validation in sonar imagery."""

    # -------------------------------------------------------------------------
    # 1. Shadow Candidate Extraction
    # -------------------------------------------------------------------------

    def extract_shadow_candidates(
        self,
        image_gray: np.ndarray,
        highlight_bbox: BoundingBox,
        search_radius_factor: float = 3.0,
    ) -> List[Tuple[np.ndarray, Tuple[int, int, int, int], float, float, float]]:
        """
        Extract dark acoustic shadow candidate regions in the vicinity of the highlight.

        Returns:
            List of (contour, (x, y, w, h), mean_intensity, area, ambient_median)
            sorted by darkness and area.
        """
        img_h, img_w = image_gray.shape[:2]

        # Define search Region of Interest (ROI) around detection highlight
        hx1, hy1 = int(highlight_bbox.x_min), int(highlight_bbox.y_min)
        hx2, hy2 = int(highlight_bbox.x_max), int(highlight_bbox.y_max)
        hw = max(1, hx2 - hx1)
        hh = max(1, hy2 - hy1)

        pad_x = int(hw * search_radius_factor)
        pad_y = int(hh * search_radius_factor)

        rx1 = max(0, hx1 - pad_x)
        ry1 = max(0, hy1 - pad_y)
        rx2 = min(img_w, hx2 + pad_x)
        ry2 = min(img_h, hy2 + pad_y)

        roi = image_gray[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return []

        # Mask out the detection highlight itself to sample ambient seabed background
        local_mask = np.ones(roi.shape, dtype=np.uint8) * 255
        lhx1 = max(0, hx1 - rx1)
        lhy1 = max(0, hy1 - ry1)
        lhx2 = min(roi.shape[1], hx2 - rx1)
        lhy2 = min(roi.shape[0], hy2 - ry1)
        local_mask[lhy1:lhy2, lhx1:lhx2] = 0

        seabed_pixels = roi[local_mask > 0]
        if len(seabed_pixels) < 10:
            ambient_median = float(np.median(roi))
            ambient_std = float(np.std(roi))
        else:
            ambient_median = float(np.median(seabed_pixels))
            ambient_std = float(np.std(seabed_pixels))

        # Threshold dark acoustic shadow pixels
        dark_cutoff = max(8, int(ambient_median - 0.6 * max(10.0, ambient_std)))
        shadow_mask = np.zeros_like(roi, dtype=np.uint8)
        shadow_mask[roi < dark_cutoff] = 255
        # Ensure highlight area is excluded from being counted as shadow
        shadow_mask[lhy1:lhy2, lhx1:lhx2] = 0

        # Morphological cleanup (remove salt-and-pepper speckle and bridge small gaps)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_OPEN, kernel)
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        shadow_mask = cv2.morphologyEx(shadow_mask, cv2.MORPH_CLOSE, kernel_close)

        contours, _ = cv2.findContours(shadow_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = max(15.0, (hw * hh) * 0.15)
        candidates = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue

            # Convert local contour coordinates back to global image coordinates
            cnt_global = cnt.copy()
            cnt_global[:, :, 0] += rx1
            cnt_global[:, :, 1] += ry1

            bx, by, bw, bh = cv2.boundingRect(cnt_global)

            # Compute mean pixel intensity inside shadow contour
            c_mask = np.zeros_like(image_gray, dtype=np.uint8)
            cv2.drawContours(c_mask, [cnt_global], -1, 255, -1)
            mean_intensity = float(cv2.mean(image_gray, mask=c_mask)[0])

            candidates.append((cnt_global, (bx, by, bw, bh), mean_intensity, area, ambient_median))

        # Sort candidates: prioritize dark, substantial regions near the highlight
        if not candidates:
            return []

        # Sort by lowest intensity (darkest) and largest area
        candidates.sort(key=lambda c: (c[2] - 0.05 * math.sqrt(c[3])))
        return candidates

    # -------------------------------------------------------------------------
    # 2. Spatial Relationship
    # -------------------------------------------------------------------------

    def analyze_spatial_relationship(
        self,
        highlight_bbox: BoundingBox,
        shadow_bbox: Tuple[int, int, int, int],
        shadow_contour: np.ndarray,
    ) -> SpatialRelationship:
        """Measure vector displacement, gap separation, and adjacency."""
        # Highlight centroid
        hc_x = (highlight_bbox.x_min + highlight_bbox.x_max) / 2.0
        hc_y = (highlight_bbox.y_min + highlight_bbox.y_max) / 2.0

        # Shadow centroid (from image moments for precision)
        M = cv2.moments(shadow_contour)
        if M["m00"] != 0:
            sc_x = float(M["m10"] / M["m00"])
            sc_y = float(M["m01"] / M["m00"])
        else:
            sx, sy, sw, sh = shadow_bbox
            sc_x = sx + sw / 2.0
            sc_y = sy + sh / 2.0

        dx = sc_x - hc_x
        dy = sc_y - hc_y
        dist = math.hypot(dx, dy)

        # Boundary gap distance
        sx, sy, sw, sh = shadow_bbox
        gap_x = max(0.0, float(sx) - highlight_bbox.x_max, highlight_bbox.x_min - float(sx + sw))
        gap_y = max(0.0, float(sy) - highlight_bbox.y_max, highlight_bbox.y_min - float(sy + sh))
        boundary_gap = math.hypot(gap_x, gap_y)

        # Proximity tolerance based on highlight dimension
        max_dim = max(highlight_bbox.width, highlight_bbox.height)
        is_adjacent = boundary_gap <= max(12.0, max_dim * 0.35)

        return SpatialRelationship(
            highlight_centroid=(round(hc_x, 2), round(hc_y, 2)),
            shadow_centroid=(round(sc_x, 2), round(sc_y, 2)),
            offset_dx=round(dx, 2),
            offset_dy=round(dy, 2),
            euclidean_distance_pixels=round(dist, 2),
            boundary_gap_pixels=round(boundary_gap, 2),
            is_adjacent=is_adjacent,
        )

    # -------------------------------------------------------------------------
    # 3. Direction
    # -------------------------------------------------------------------------

    def analyze_direction(
        self,
        spatial_rel: SpatialRelationship,
        nadir_x: Optional[float] = None,
        sensor_pos: Optional[Tuple[float, float]] = None,
    ) -> ShadowDirection:
        """
        Calculate shadow projection angle and evaluate consistency with acoustic ray transmission.
        """
        dx = spatial_rel.offset_dx
        dy = spatial_rel.offset_dy

        # Angle in degrees [0, 360), 0 deg = East / Positive X
        angle_rad = math.atan2(dy, dx)
        angle_deg = (math.degrees(angle_rad) + 360.0) % 360.0

        # Cardinal direction mapping
        cardinals = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"]
        idx = int((angle_deg + 22.5) / 45.0) % 8
        cardinal = cardinals[idx]

        expected_deg = None
        alignment_score = 1.0

        # Evaluate against sidescan sonar nadir line geometry
        if nadir_x is not None:
            hc_x = spatial_rel.highlight_centroid[0]
            # If target is starboard (right of nadir), sound radiates rightward (~0 deg / East)
            # If target is port (left of nadir), sound radiates leftward (~180 deg / West)
            expected_deg = 0.0 if hc_x >= nadir_x else 180.0
            diff_rad = math.radians(angle_deg - expected_deg)
            # Cosine alignment: 1.0 if perfectly parallel, 0.0 if perpendicular/opposite
            alignment_score = max(0.0, math.cos(diff_rad))

        elif sensor_pos is not None:
            # Forward-looking sonar: radiating outward from transducer head (sx, sy)
            sx, sy = sensor_pos
            hc_x, hc_y = spatial_rel.highlight_centroid
            expected_rad = math.atan2(hc_y - sy, hc_x - sx)
            expected_deg = (math.degrees(expected_rad) + 360.0) % 360.0
            diff_rad = math.radians(angle_deg - expected_deg)
            alignment_score = max(0.0, math.cos(diff_rad))

        return ShadowDirection(
            angle_degrees=round(angle_deg, 2),
            cardinal_direction=cardinal,
            expected_direction_degrees=round(expected_deg, 2) if expected_deg is not None else None,
            direction_alignment_score=round(float(alignment_score), 3),
        )

    # -------------------------------------------------------------------------
    # 4. Extent (Geometry & Hydrographic Elevation)
    # -------------------------------------------------------------------------

    def measure_extent(
        self,
        shadow_contour: np.ndarray,
        shadow_direction: ShadowDirection,
        meters_per_pixel: Optional[float] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> ShadowExtent:
        """
        Measure oriented length along projection ray, width across ray, and estimate target height.
        """
        area = float(cv2.contourArea(shadow_contour))
        rect = cv2.minAreaRect(shadow_contour)
        (_, _), (rw, rh), _ = rect

        dim1, dim2 = max(rw, rh), min(rw, rh)
        length_px = max(1.0, dim1)
        width_px = max(1.0, dim2)
        aspect_ratio = length_px / width_px

        estimated_height_m = None
        if meters_per_pixel and meters_per_pixel > 0.0:
            length_m = length_px * meters_per_pixel
            if sensor_altitude_m and slant_range_m and slant_range_m > 0.0:
                # Hydrographic formula: h = (L_shadow * Altitude) / (SlantRange + L_shadow)
                h = (length_m * sensor_altitude_m) / (slant_range_m + length_m)
                estimated_height_m = round(float(h), 2)

        return ShadowExtent(
            length_pixels=round(length_px, 2),
            width_pixels=round(width_px, 2),
            aspect_ratio=round(aspect_ratio, 2),
            area_pixels=round(area, 2),
            estimated_object_height_m=estimated_height_m,
        )

    # -------------------------------------------------------------------------
    # 5. Shadow Score Computation
    # -------------------------------------------------------------------------

    def compute_shadow_score(
        self,
        ambient_median: float,
        shadow_mean: float,
        spatial_rel: SpatialRelationship,
        direction: ShadowDirection,
        extent: ShadowExtent,
        highlight_bbox: BoundingBox,
    ) -> Tuple[float, float, str]:
        """
        Compute multi-factor composite shadow score in [0.0 - 1.0] and confidence adjustment.
        """
        # Factor 1: Contrast Darkness (30%) - How dark is the shadow compared to surrounding seabed?
        contrast_diff = max(0.0, ambient_median - shadow_mean)
        contrast_score = min(1.0, contrast_diff / max(15.0, ambient_median * 0.65))

        # Factor 2: Proximity / Adjacency (25%) - Is the shadow touching/adjacent to the highlight?
        max_h_dim = max(highlight_bbox.width, highlight_bbox.height)
        adjacency_score = math.exp(-spatial_rel.boundary_gap_pixels / max(12.0, max_h_dim * 0.6))

        # Factor 3: Directional Alignment (25%) - Does shadow cast along the acoustic ray?
        direction_score = direction.direction_alignment_score

        # Factor 4: Geometric Proportion (20%) - Is shadow width comparable to target width?
        width_ratio = min(1.0, extent.width_pixels / max(1.0, highlight_bbox.width * 0.6))
        geometry_score = max(0.2, width_ratio)

        # Composite score
        total_score = (
            0.30 * contrast_score +
            0.25 * adjacency_score +
            0.25 * direction_score +
            0.20 * geometry_score
        )
        total_score = max(0.0, min(1.0, total_score))

        # Confidence adjustment and quality tier
        if total_score >= 0.70:
            quality = "Strong Shadow - High Physical Confidence"
            conf_adj = +0.12
        elif total_score >= 0.50:
            quality = "Moderate Shadow - Probable 3D Structure"
            conf_adj = +0.06
        elif total_score >= 0.30:
            quality = "Weak / Ambiguous Shadow"
            conf_adj = 0.00
        else:
            quality = "Poor / Marginal Shadow"
            conf_adj = -0.08

        return round(total_score, 3), round(conf_adj, 3), quality

    # -------------------------------------------------------------------------
    # End-to-End Analysis for a Single Detection Item
    # -------------------------------------------------------------------------

    def analyze_detection_shadow(
        self,
        image_gray: np.ndarray,
        detection_id: str,
        class_name: str,
        bbox: BoundingBox,
        nadir_x: Optional[float] = None,
        sensor_pos: Optional[Tuple[float, float]] = None,
        meters_per_pixel: Optional[float] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> ShadowAnalysisResult:
        """Execute the 6-stage highlight-shadow analytics pipeline on a single detection."""
        candidates = self.extract_shadow_candidates(image_gray, bbox)

        if not candidates:
            return ShadowAnalysisResult(
                detection_id=detection_id,
                class_name=class_name,
                has_shadow=False,
                shadow_score=0.0,
                confidence_adjustment=-0.10,
                candidate=None,
                spatial_relationship=None,
                direction=None,
                extent=None,
                quality_assessment="No Shadow Detected - Likely Flat Anomaly",
            )

        # Primary candidate
        cnt, (bx, by, bw, bh), mean_int, area, amb_med = candidates[0]

        cand_bbox = BoundingBox(
            x_min=float(bx),
            y_min=float(by),
            x_max=float(bx + bw),
            y_max=float(by + bh),
            width=float(bw),
            height=float(bh),
            normalized_x_min=round(bx / image_gray.shape[1], 4),
            normalized_y_min=round(by / image_gray.shape[0], 4),
            normalized_x_max=round((bx + bw) / image_gray.shape[1], 4),
            normalized_y_max=round((by + bh) / image_gray.shape[0], 4),
        )

        M = cv2.moments(cnt)
        sc_x = float(M["m10"] / M["m00"]) if M["m00"] != 0 else bx + bw / 2.0
        sc_y = float(M["m01"] / M["m00"]) if M["m00"] != 0 else by + bh / 2.0

        # Simplified polygon contour points for UI overlay
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        contour_pts = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]

        candidate = ShadowCandidate(
            candidate_id=f"shd_{uuid.uuid4().hex[:8]}",
            bbox=cand_bbox,
            centroid=(round(sc_x, 2), round(sc_y, 2)),
            contour_points=contour_pts,
            area_pixels=round(area, 2),
            mean_intensity=round(mean_int, 2),
        )

        # Spatial relationship
        spatial_rel = self.analyze_spatial_relationship(bbox, (bx, by, bw, bh), cnt)

        # Direction
        direction = self.analyze_direction(spatial_rel, nadir_x=nadir_x, sensor_pos=sensor_pos)

        # Extent
        extent = self.measure_extent(
            cnt,
            direction,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )

        # Score
        score, conf_adj, quality = self.compute_shadow_score(
            ambient_median=amb_med,
            shadow_mean=mean_int,
            spatial_rel=spatial_rel,
            direction=direction,
            extent=extent,
            highlight_bbox=bbox,
        )

        return ShadowAnalysisResult(
            detection_id=detection_id,
            class_name=class_name,
            has_shadow=True,
            shadow_score=score,
            confidence_adjustment=conf_adj,
            candidate=candidate,
            spatial_relationship=spatial_rel,
            direction=direction,
            extent=extent,
            quality_assessment=quality,
        )

    # -------------------------------------------------------------------------
    # Batch Orchestration across All Detections
    # -------------------------------------------------------------------------

    def analyze_all_detections(
        self,
        image_bgr: np.ndarray,
        detections: List[Dict[str, Any]],
        nadir_x: Optional[float] = None,
        sensor_pos: Optional[Tuple[float, float]] = None,
        meters_per_pixel: Optional[float] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
        return_overlay: bool = True,
    ) -> ShadowAnalysisResponse:
        """
        Run acoustic shadow pipeline for all detections on a sonar image.
        """
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if len(image_bgr.shape) == 3 else image_bgr

        results: List[ShadowAnalysisResult] = []
        confirmed_count = 0
        score_sum = 0.0

        for det in detections:
            bbox_dict = det.get("bbox", {})
            bbox = BoundingBox(
                x_min=float(bbox_dict.get("x_min", 0)),
                y_min=float(bbox_dict.get("y_min", 0)),
                x_max=float(bbox_dict.get("x_max", 0)),
                y_max=float(bbox_dict.get("y_max", 0)),
                width=float(bbox_dict.get("width", 0)),
                height=float(bbox_dict.get("height", 0)),
                normalized_x_min=float(bbox_dict.get("normalized_x_min", 0)),
                normalized_y_min=float(bbox_dict.get("normalized_y_min", 0)),
                normalized_x_max=float(bbox_dict.get("normalized_x_max", 0)),
                normalized_y_max=float(bbox_dict.get("normalized_y_max", 0)),
            )

            res = self.analyze_detection_shadow(
                image_gray=gray,
                detection_id=det.get("detection_id", "unknown"),
                class_name=det.get("class_name", "debris"),
                bbox=bbox,
                nadir_x=nadir_x,
                sensor_pos=sensor_pos,
                meters_per_pixel=meters_per_pixel,
                sensor_altitude_m=sensor_altitude_m,
                slant_range_m=slant_range_m,
            )
            results.append(res)
            if res.has_shadow and res.shadow_score >= 0.40:
                confirmed_count += 1
            score_sum += res.shadow_score

        avg_score = round(score_sum / max(1, len(results)), 3)

        overlay_b64 = None
        if return_overlay:
            overlay_bgr = self.render_shadow_overlay(image_bgr, results)
            overlay_b64 = encode_image_to_base64(overlay_bgr)

        return ShadowAnalysisResponse(
            status="success",
            total_detections_analyzed=len(detections),
            shadows_confirmed=confirmed_count,
            average_shadow_score=avg_score,
            results=results,
            annotated_overlay_base64=overlay_b64,
        )

    # -------------------------------------------------------------------------
    # Visual Overlay Renderer
    # -------------------------------------------------------------------------

    def render_shadow_overlay(
        self,
        image_bgr: np.ndarray,
        shadow_results: List[ShadowAnalysisResult],
        skip_detection_ids: Optional[set] = None,
    ) -> np.ndarray:
        """
        Draw highlight boxes (yellow), shadow polygons (cyan/blue), and projection arrows.
        Shadow evidence for detections in `skip_detection_ids` (e.g. rejected false alarms)
        is omitted so the overlay only shows corroboration for kept targets.
        """
        annotated = image_bgr.copy()
        skip_detection_ids = skip_detection_ids or set()

        for res in shadow_results:
            if not res.has_shadow or not res.candidate:
                continue
            if getattr(res, "detection_id", None) in skip_detection_ids:
                continue

            cand = res.candidate
            spat = res.spatial_relationship

            # Draw a thin outline so shadow evidence does not hide the sonar image.
            if cand.contour_points and len(cand.contour_points) >= 3:
                pts = np.array(cand.contour_points, dtype=np.int32).reshape((-1, 1, 2))
                x, y, width, height = cv2.boundingRect(pts)
                image_height, image_width = annotated.shape[:2]
                oversized = width > image_width * 0.75 or height > image_height * 0.75
                # Tall, thin strip near the image center = nadir / water-column artifact,
                # not a real object shadow — don't draw it.
                cx = x + width / 2.0
                nadir_like = (
                    height > image_height * 0.30
                    and width < image_width * 0.12
                    and abs(cx - image_width / 2.0) < image_width * 0.15
                )
                if not oversized and not nadir_like:
                    cv2.polylines(annotated, [pts], True, (255, 255, 0), 2)  # Cyan outline

            # Draw acoustic projection vector arrow from highlight to shadow
            if spat:
                hx, hy = int(spat.highlight_centroid[0]), int(spat.highlight_centroid[1])
                sx, sy = int(spat.shadow_centroid[0]), int(spat.shadow_centroid[1])
                cv2.arrowedLine(annotated, (hx, hy), (sx, sy), (0, 255, 255), 2, tipLength=0.2)

                # Draw score tag
                tag_text = f"Shadow: {int(res.shadow_score * 100)}%"
                if res.extent and res.extent.estimated_object_height_m:
                    tag_text += f" | H: {res.extent.estimated_object_height_m}m"

                cv2.putText(
                    annotated,
                    tag_text,
                    (sx + 5, sy - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        return annotated


# Global service instance
shadow_service = ShadowService()
