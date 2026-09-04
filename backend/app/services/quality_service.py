"""
Acoustic Image Quality Assessment Service for MarineScan.
Handles Stage 2 of the Master Pipeline:
Evaluates global acoustic sharpness, RMS contrast, noise variance,
dynamic range, and blackout/saturation clipping before model execution.
"""

import logging
from typing import List
import cv2
import numpy as np

from app.schemas.analysis import QualityAssessment, QualityTier

logger = logging.getLogger("marinescan.services.quality")


class QualityService:
    """Acoustic image health and telemetry evaluation engine."""

    def evaluate_image_quality(self, image_bgr: np.ndarray) -> QualityAssessment:
        """
        Compute comprehensive acoustic quality metrics on full image.
        """
        if len(image_bgr.shape) == 3 and image_bgr.shape[2] == 3:
            gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_bgr.copy()

        # 1. Laplacian Focus Sharpness
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        lap_var = float(laplacian.var())

        # 2. RMS Contrast
        mean_intensity = float(np.mean(gray))
        std_intensity = float(np.std(gray))
        rms_contrast = (std_intensity / max(1.0, mean_intensity))

        # 3. Dynamic Range & SNR Estimation
        p5 = float(np.percentile(gray, 5))
        p95 = float(np.percentile(gray, 95))
        dyn_range = max(1.0, p95 - p5)

        # Estimated SNR: signal (std) vs background residual noise
        smoothed = cv2.GaussianBlur(gray, (5, 5), 0)
        noise_diff = gray.astype(np.float32) - smoothed.astype(np.float32)
        noise_var = float(np.var(noise_diff))
        if noise_var > 0:
            snr_db = 10.0 * np.log10(max(1.0, (std_intensity ** 2) / noise_var))
        else:
            snr_db = 30.0

        # 4. Exposure Clipping
        total_pixels = float(gray.size)
        blackout_pixels = float(np.sum(gray <= 4))
        saturated_pixels = float(np.sum(gray >= 252))

        under_ratio = blackout_pixels / total_pixels
        over_ratio = saturated_pixels / total_pixels

        # 5. Composite Normalized Quality Score [0 - 1]
        sharp_norm = min(1.0, lap_var / 500.0)
        contrast_norm = min(1.0, rms_contrast / 0.8)
        dyn_norm = min(1.0, dyn_range / 180.0)

        # Penalty for excessive clipping
        clip_penalty = min(0.5, (under_ratio * 0.7) + (over_ratio * 0.8))

        overall_score = (
            0.40 * sharp_norm +
            0.35 * contrast_norm +
            0.25 * dyn_norm
        ) - clip_penalty
        overall_score = max(0.05, min(1.0, overall_score))

        # 6. Quality Tier Classification
        quality_notes: List[str] = []

        if overall_score >= 0.75:
            tier = QualityTier.PRISTINE
            quality_notes.append("High-resolution, well-defined acoustic returns.")
        elif overall_score >= 0.55:
            tier = QualityTier.GOOD
            quality_notes.append("Good acoustic contrast suitable for standard detection.")
        elif overall_score >= 0.35:
            tier = QualityTier.ACCEPTABLE
            quality_notes.append("Acceptable quality; mild speckle noise or contrast attenuation.")
        elif overall_score >= 0.20:
            tier = QualityTier.DEGRADED
            quality_notes.append("Degraded acoustic quality; CLAHE preprocessing recommended.")
        else:
            tier = QualityTier.UNUSABLE
            quality_notes.append("Severely degraded acoustic scan; high risk of missed targets.")

        if lap_var < 50.0:
            quality_notes.append("Low Laplacian variance indicates acoustic defocus or motion blur.")
        if under_ratio > 0.40:
            quality_notes.append("Extensive acoustic blackout regions detected (possible water column gap or attenuation).")
        if over_ratio > 0.25:
            quality_notes.append("Significant acoustic saturation detected (receiver gain may be set too high).")

        is_usable = tier != QualityTier.UNUSABLE

        return QualityAssessment(
            laplacian_sharpness=round(lap_var, 2),
            rms_contrast=round(rms_contrast, 3),
            snr_db=round(snr_db, 2),
            underexposed_ratio=round(under_ratio, 4),
            overexposed_ratio=round(over_ratio, 4),
            overall_quality_score=round(overall_score, 3),
            quality_tier=tier,
            is_usable_for_mission=is_usable,
            quality_notes=quality_notes,
        )


# Global service instance
quality_service = QualityService()
