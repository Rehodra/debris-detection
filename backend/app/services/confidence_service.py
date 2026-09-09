"""
Confidence Service for MarineScan.
Synthesizes AI Detection Confidence, Physics & Shadow Evidence, and Acoustic Image Quality
into a calibrated, explainable trust metric.
"""

import math
import logging
from typing import Optional, List, Dict, Any, Tuple

import cv2
import numpy as np

from app.schemas.confidence import (
    TrustTier,
    ImageQualityMetrics,
    ConfidencePillars,
    TargetConfidenceProfile,
    BatchConfidenceResponse,
)
from app.schemas.detection import BoundingBox, DetectionItem
from app.schemas.shadow import ShadowAnalysisResult
from app.schemas.physics import TargetPhysicsAnalysis
from app.services.physics_service import physics_service
from app.services.shadow_service import shadow_service

logger = logging.getLogger("marinescan.services.confidence")


class ConfidenceService:
    """Production service for multi-source confidence fusion, calibration, and explainability."""

    # -------------------------------------------------------------------------
    # 1. Local Image Quality Assessment
    # -------------------------------------------------------------------------

    def assess_local_image_quality(
        self,
        image_gray: np.ndarray,
        bbox: BoundingBox,
        padding_factor: float = 1.3,
    ) -> ImageQualityMetrics:
        """
        Assess acoustic image quality in the local ROI of the detected target:
        - Sharpness via Laplacian gradient variance
        - RMS contrast and dynamic range
        - Saturation/blackout exposure penalties
        """
        img_h, img_w = image_gray.shape[:2]

        # Crop local Region of Interest (ROI) with contextual padding
        pad_x = int(bbox.width * (padding_factor - 1.0) / 2.0)
        pad_y = int(bbox.height * (padding_factor - 1.0) / 2.0)

        rx1 = max(0, int(bbox.x_min) - pad_x)
        ry1 = max(0, int(bbox.y_min) - pad_y)
        rx2 = min(img_w, int(bbox.x_max) + pad_x)
        ry2 = min(img_h, int(bbox.y_max) + pad_y)

        roi = image_gray[ry1:ry2, rx1:rx2]
        if roi.size < 9:
            roi = image_gray

        # 1. Sharpness: Laplacian variance
        lap = cv2.Laplacian(roi, cv2.CV_64F)
        lap_var = float(lap.var())
        # Benchmark: variance ~250 in clean sonar edges -> normalized 1.0
        sharpness_score = min(1.0, max(0.05, lap_var / 220.0))

        # 2. Contrast & Dynamic Range
        mean_val = float(np.mean(roi))
        std_val = float(np.std(roi))
        # Normalized contrast: std of 45 -> score 1.0
        contrast_score = min(1.0, max(0.05, std_val / 42.0))

        # 3. Exposure / Clipping Penalty
        total_pixels = float(roi.size)
        saturated_pixels = float(np.sum(roi >= 252))
        blackout_pixels = float(np.sum(roi <= 3))
        clipping_frac = (saturated_pixels + blackout_pixels) / total_pixels
        exposure_penalty = min(0.60, clipping_frac * 2.5)
        exposure_score = max(0.10, 1.0 - exposure_penalty)

        # Composite local quality
        overall = (
            0.40 * contrast_score +
            0.35 * sharpness_score +
            0.25 * exposure_score
        )
        overall = max(0.0, min(1.0, overall))

        if overall >= 0.75:
            tier = "Pristine"
        elif overall >= 0.55:
            tier = "Good"
        elif overall >= 0.35:
            tier = "Moderate"
        else:
            tier = "Degraded / Noisy"

        return ImageQualityMetrics(
            sharpness_score=round(sharpness_score, 3),
            contrast_score=round(contrast_score, 3),
            exposure_score=round(exposure_score, 3),
            overall_quality_score=round(overall, 3),
            quality_tier=tier,
        )

    # -------------------------------------------------------------------------
    # 2. Physics & Shadow Score Synthesis
    # -------------------------------------------------------------------------

    def calculate_physics_confidence(
        self,
        class_name: str,
        length_m: float,
        width_m: float,
        shadow_result: Optional[ShadowAnalysisResult] = None,
        physics_analysis: Optional[TargetPhysicsAnalysis] = None,
    ) -> Tuple[float, bool, bool, List[str]]:
        """
        Synthesize acoustic shadow evidence and physical dimensional plausibility.

        Returns:
            Tuple: (physics_score [0 - 1], has_shadow_corroboration, is_plausible, notes)
        """
        notes: List[str] = []
        c_lower = class_name.lower()

        # 1. Acoustic Shadow Corroboration
        has_shadow = False
        shadow_component = 0.30

        if shadow_result and shadow_result.has_shadow:
            has_shadow = True
            raw_shadow_score = shadow_result.shadow_score
            if raw_shadow_score >= 0.70:
                shadow_component = 1.0
                notes.append(f"Strong 3D acoustic shadow verified (score: {int(raw_shadow_score * 100)}%).")
            elif raw_shadow_score >= 0.40:
                shadow_component = 0.75
                notes.append(f"Moderate acoustic shadow corroborates target relief (score: {int(raw_shadow_score * 100)}%).")
            else:
                shadow_component = 0.45
                notes.append(f"Faint acoustic shadow detected (score: {int(raw_shadow_score * 100)}%).")
        else:
            # Shadow absent
            if c_lower in ["shipwreck", "aircraft", "pipe"]:
                shadow_component = 0.20
                notes.append(f"Absence of acoustic shadow for large {class_name} suggests potential flat seabed anomaly.")
            else:
                shadow_component = 0.40
                notes.append("No distinct acoustic shadow detected.")

        # 2. Dimensional Plausibility
        if physics_analysis:
            dim_score = physics_analysis.plausibility.physical_validation_score
            is_plausible = physics_analysis.plausibility.is_plausible
            notes.extend(physics_analysis.plausibility.plausibility_notes)
        else:
            # Fallback direct check via physics service
            plaus = physics_service.verify_physical_plausibility(
                class_name=class_name,
                length_m=length_m,
                width_m=width_m,
                height_m=min(length_m, width_m) * 0.4,
                has_shadow_evidence=has_shadow,
            )
            dim_score = plaus.physical_validation_score
            is_plausible = plaus.is_plausible
            notes.extend(plaus.plausibility_notes)

        # Composite Physics Score (55% shadow corroboration, 45% dimensional plausibility)
        physics_score = 0.55 * shadow_component + 0.45 * dim_score
        physics_score = max(0.0, min(1.0, physics_score))

        return round(physics_score, 3), has_shadow, is_plausible, notes

    # -------------------------------------------------------------------------
    # 3. Calibrated Confidence Fusion
    # -------------------------------------------------------------------------

    def fuse_confidence(
        self,
        ai_conf: float,
        physics_score: float,
        quality_score: float,
        is_plausible: bool,
    ) -> Tuple[float, float, TrustTier, Dict[str, float]]:
        """
        Calibrate multi-source confidence using adaptive weights and plausibility gating.
        """
        # Adaptive weight distribution
        if quality_score < 0.40:
            # In degraded / noisy sonar, shift reliance toward physics verification
            w_ai = 0.35
            w_phys = 0.45
            w_qual = 0.20
        else:
            w_ai = 0.45
            w_phys = 0.35
            w_qual = 0.20

        raw_fused = (w_ai * ai_conf) + (w_phys * physics_score) + (w_qual * quality_score)

        # Plausibility Gate: heavily penalize physically impossible objects (e.g. 400m aircraft)
        if not is_plausible:
            calibrated = raw_fused * 0.55
        else:
            calibrated = raw_fused

        calibrated = max(0.05, min(0.99, calibrated))
        delta = round(calibrated - ai_conf, 3)

        # Trust Tier Classification
        if calibrated >= 0.80:
            tier = TrustTier.VERIFIED_TARGET
        elif calibrated >= 0.60:
            tier = TrustTier.PROBABLE_DEBRIS
        elif calibrated >= 0.40:
            tier = TrustTier.AMBIGUOUS_ANOMALY
        else:
            tier = TrustTier.SUSPECTED_FALSE_ALARM

        weights = {"ai": w_ai, "physics": w_phys, "quality": w_qual}
        return round(calibrated, 3), delta, tier, weights

    # -------------------------------------------------------------------------
    # 4. End-to-End Single Target Evaluation
    # -------------------------------------------------------------------------

    def evaluate_target_confidence(
        self,
        image_gray: np.ndarray,
        detection_id: str,
        class_name: str,
        raw_ai_confidence: float,
        bbox: BoundingBox,
        length_m: float,
        width_m: float,
        shadow_result: Optional[ShadowAnalysisResult] = None,
        physics_analysis: Optional[TargetPhysicsAnalysis] = None,
    ) -> TargetConfidenceProfile:
        """
        Execute full confidence fusion pipeline on a single detected target.
        """
        # Pillar 1: Image Quality
        quality = self.assess_local_image_quality(image_gray, bbox)

        # Pillar 2: Physics & Shadow Evidence
        phys_score, has_shadow, is_plausible, phys_notes = self.calculate_physics_confidence(
            class_name=class_name,
            length_m=length_m,
            width_m=width_m,
            shadow_result=shadow_result,
            physics_analysis=physics_analysis,
        )

        # Pillar 3: Fusion & Calibration
        calibrated_conf, delta, tier, weights = self.fuse_confidence(
            ai_conf=raw_ai_confidence,
            physics_score=phys_score,
            quality_score=quality.overall_quality_score,
            is_plausible=is_plausible,
        )

        # Explainability synthesis
        explanation_notes: List[str] = []
        explanation_notes.append(f"Raw neural network detection confidence: {int(raw_ai_confidence * 100)}%.")
        explanation_notes.extend(phys_notes)
        explanation_notes.append(f"Local acoustic imaging quality assessed as '{quality.quality_tier}' (score: {quality.overall_quality_score:.2f}).")

        if delta > 0.02:
            explanation_notes.append(f"Calibrated confidence boosted by +{int(delta * 100)}% due to corroborating physics and acoustics.")
        elif delta < -0.02:
            explanation_notes.append(f"Calibrated confidence tempered by {int(delta * 100)}% due to acoustic uncertainty or lack of 3D shadow.")
        else:
            explanation_notes.append("Calibrated confidence closely matches raw AI assessment.")

        explanation_notes.append(f"Assigned trust classification: {tier.value}.")

        pillars = ConfidencePillars(
            ai_confidence=round(raw_ai_confidence, 3),
            physics_score=round(phys_score, 3),
            image_quality_score=quality.overall_quality_score,
            weights=weights,
        )

        return TargetConfidenceProfile(
            detection_id=detection_id,
            class_name=class_name,
            raw_ai_confidence=round(raw_ai_confidence, 3),
            calibrated_confidence=calibrated_conf,
            confidence_delta=delta,
            trust_tier=tier,
            pillars=pillars,
            quality_metrics=quality,
            has_shadow_corroboration=has_shadow,
            is_physically_plausible=is_plausible,
            explanation_notes=explanation_notes,
        )

    # -------------------------------------------------------------------------
    # 5. Batch Evaluation across Image Detections
    # -------------------------------------------------------------------------

    def evaluate_all_detections(
        self,
        image_gray: np.ndarray,
        detections: List[Dict[str, Any]],
        shadow_results: Optional[List[ShadowAnalysisResult]] = None,
        physics_analyses: Optional[List[TargetPhysicsAnalysis]] = None,
        meters_per_pixel: float = 0.05,
    ) -> BatchConfidenceResponse:
        """
        Evaluate and calibrate confidence across all detections in an image.
        """
        shadow_map = {r.detection_id: r for r in (shadow_results or [])}
        phys_map = {p.detection_id: p for p in (physics_analyses or [])}

        results: List[TargetConfidenceProfile] = []
        verified_count = 0
        total_conf = 0.0

        for det in detections:
            det_id = det.get("detection_id", "unknown")
            cname = det.get("class_name", "other")
            ai_conf = float(det.get("confidence", 0.5))

            bbox_dict = det.get("bbox", {})
            bbox = BoundingBox(
                x_min=float(bbox_dict.get("x_min", 0)),
                y_min=float(bbox_dict.get("y_min", 0)),
                x_max=float(bbox_dict.get("x_max", 0)),
                y_max=float(bbox_dict.get("y_max", 0)),
                width=float(bbox_dict.get("width", 50)),
                height=float(bbox_dict.get("height", 50)),
                normalized_x_min=float(bbox_dict.get("normalized_x_min", 0)),
                normalized_y_min=float(bbox_dict.get("normalized_y_min", 0)),
                normalized_x_max=float(bbox_dict.get("normalized_x_max", 0)),
                normalized_y_max=float(bbox_dict.get("normalized_y_max", 0)),
            )

            # Dimensions
            phys_dim = det.get("physical_dimensions")
            if phys_dim and "length_meters" in phys_dim and "width_meters" in phys_dim:
                l_m = float(phys_dim["length_meters"])
                w_m = float(phys_dim["width_meters"])
            else:
                l_m = max(bbox.width, bbox.height) * meters_per_pixel
                w_m = min(bbox.width, bbox.height) * meters_per_pixel

            profile = self.evaluate_target_confidence(
                image_gray=image_gray,
                detection_id=det_id,
                class_name=cname,
                raw_ai_confidence=ai_conf,
                bbox=bbox,
                length_m=l_m,
                width_m=w_m,
                shadow_result=shadow_map.get(det_id),
                physics_analysis=phys_map.get(det_id),
            )
            results.append(profile)

            if profile.trust_tier == TrustTier.VERIFIED_TARGET:
                verified_count += 1
            total_conf += profile.calibrated_confidence

        avg_conf = round(total_conf / max(1, len(results)), 3)

        return BatchConfidenceResponse(
            status="success",
            total_targets_evaluated=len(detections),
            verified_targets_count=verified_count,
            average_calibrated_confidence=avg_conf,
            results=results,
        )


# Global service instance
confidence_service = ConfidenceService()
