"""
Pydantic schemas for Multi-Source Confidence Calibration & Explainability.
Models the three confidence pillars (AI model, physics & shadow score, image quality),
calibrated fusion scores, trust tiers, and explainability breakdowns.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class TrustTier(str, Enum):
    VERIFIED_TARGET = "VERIFIED_TARGET"           # >= 0.80: Corroborated by clean acoustics & shadow
    PROBABLE_DEBRIS = "PROBABLE_DEBRIS"           # 0.60 - 0.79: Strong candidate
    AMBIGUOUS_ANOMALY = "AMBIGUOUS_ANOMALY"       # 0.40 - 0.59: Uncertain, needs closer pass
    SUSPECTED_FALSE_ALARM = "SUSPECTED_FALSE_ALARM" # < 0.40: Low quality or physically implausible


class ImageQualityMetrics(BaseModel):
    sharpness_score: float = Field(..., ge=0.0, le=1.0, description="Normalized Laplacian edge sharpness [0 - 1]")
    contrast_score: float = Field(..., ge=0.0, le=1.0, description="Normalized RMS contrast and dynamic range [0 - 1]")
    exposure_score: float = Field(..., ge=0.0, le=1.0, description="Penalty-free exposure quality (no saturation/dropout)")
    overall_quality_score: float = Field(..., ge=0.0, le=1.0, description="Composite local image quality score [0 - 1]")
    quality_tier: str = Field(..., description="'Pristine', 'Good', 'Moderate', or 'Degraded / Noisy'")


class ConfidencePillars(BaseModel):
    ai_confidence: float = Field(..., ge=0.0, le=1.0, description="Raw YOLO neural network detection confidence")
    physics_score: float = Field(..., ge=0.0, le=1.0, description="Physics validation & shadow corroboration score")
    image_quality_score: float = Field(..., ge=0.0, le=1.0, description="Local acoustic imaging quality score")
    weights: Dict[str, float] = Field(
        default_factory=lambda: {"ai": 0.45, "physics": 0.35, "quality": 0.20},
        description="Pillar weight distribution applied in fusion",
    )


class TargetConfidenceProfile(BaseModel):
    detection_id: str = Field(..., description="Target detection identifier")
    class_name: str = Field(..., description="Target debris class")
    raw_ai_confidence: float = Field(..., ge=0.0, le=1.0, description="Original uncalibrated AI detection confidence")
    calibrated_confidence: float = Field(..., ge=0.0, le=1.0, description="Final calibrated multi-source confidence")
    confidence_delta: float = Field(..., description="Change from raw AI confidence (+ boost or - penalty)")
    trust_tier: TrustTier = Field(..., description="Categorical trust classification")
    pillars: ConfidencePillars = Field(..., description="Detailed pillar scores")
    quality_metrics: ImageQualityMetrics = Field(..., description="Acoustic image quality breakdown")
    has_shadow_corroboration: bool = Field(..., description="True if acoustic shadow verified 3D relief")
    is_physically_plausible: bool = Field(..., description="True if target dimensions conform to maritime physics")
    explanation_notes: List[str] = Field(default_factory=list, description="Human-in-the-loop explainability rationale")


class BatchConfidenceResponse(BaseModel):
    status: str = Field("success", description="Execution status")
    total_targets_evaluated: int = Field(..., description="Total targets evaluated")
    verified_targets_count: int = Field(..., description="Targets achieving VERIFIED_TARGET tier")
    average_calibrated_confidence: float = Field(..., description="Mean calibrated confidence across all detections")
    results: List[TargetConfidenceProfile] = Field(default_factory=list, description="Per-target confidence profiles")
