"""
Pydantic schemas for the Master Analysis Pipeline.
Unifies all 12 stages: Input validation, quality checking, preprocessing,
YOLO detection/segmentation, candidate list, acoustic shadow evidence,
physics validation, confidence fusion, geolocation, dimension estimation,
risk classification, and final executive results.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from app.schemas.detection import BoundingBox, ImageMetadata
from app.schemas.confidence import TrustTier
from app.schemas.risk import RiskTier, NavigationalClearance, ActionRecommendation
from app.schemas.geolocation import GeoCoordinates, GeoJSONFeatureCollection


class QualityTier(str, Enum):
    PRISTINE = "PRISTINE"
    GOOD = "GOOD"
    ACCEPTABLE = "ACCEPTABLE"
    DEGRADED = "DEGRADED"
    UNUSABLE = "UNUSABLE"


class QualityAssessment(BaseModel):
    laplacian_sharpness: float = Field(..., description="Focus sharpness variance")
    rms_contrast: float = Field(..., description="Root-mean-square contrast")
    snr_db: float = Field(..., description="Estimated Signal-to-Noise Ratio (dB)")
    underexposed_ratio: float = Field(..., description="Fraction of blacked out acoustic pixels")
    overexposed_ratio: float = Field(..., description="Fraction of saturated acoustic pixels")
    overall_quality_score: float = Field(..., ge=0.0, le=1.0, description="Normalized image health [0 - 1]")
    quality_tier: QualityTier = Field(..., description="Acoustic quality grading")
    is_usable_for_mission: bool = Field(True, description="True if acoustic quality permits reliable inference")
    quality_notes: List[str] = Field(default_factory=list, description="Acoustic quality observations")


class StageTimings(BaseModel):
    input_validation_ms: float = Field(0.0, description="MIME & integrity check duration")
    quality_check_ms: float = Field(0.0, description="Acoustic health evaluation duration")
    preprocessing_ms: float = Field(0.0, description="Denoising & CLAHE enhancement duration")
    yolo_inference_ms: float = Field(0.0, description="Neural network inference duration")
    candidate_extraction_ms: float = Field(0.0, description="Bounding box & candidate parsing duration")
    shadow_evidence_ms: float = Field(0.0, description="Acoustic shadow extraction duration")
    physics_validation_ms: float = Field(0.0, description="Hydrodynamics & salvage mass duration")
    confidence_fusion_ms: float = Field(0.0, description="Multi-source calibration duration")
    geolocation_ms: float = Field(0.0, description="Geodesy & track-frame mapping duration")
    dimension_estimate_ms: float = Field(0.0, description="Metric 3D dimension scaling duration")
    risk_classification_ms: float = Field(0.0, description="Navigational & NOTMAR risk duration")
    total_pipeline_ms: float = Field(..., description="Total end-to-end execution duration")


class ShadowEvidence(BaseModel):
    has_shadow: bool = Field(..., description="Whether a corroborating acoustic shadow was verified")
    shadow_score: float = Field(..., ge=0.0, le=1.0, description="Shadow confidence score [0 - 1]")
    cardinal_direction: str = Field(..., description="Direction shadow propagates away from target")
    direction_degrees: float = Field(..., description="Propagation angle in degrees")
    shadow_length_m: Optional[float] = Field(None, description="Physical shadow length across seabed (m)")
    estimated_height_m: Optional[float] = Field(None, description="Calculated 3D object height off seabed (m)")


class MasterPhysicalDimensions(BaseModel):
    length_m: float = Field(..., description="Target along-track / maximum physical length (m)")
    width_m: float = Field(..., description="Target across-track physical width (m)")
    height_m: float = Field(..., description="Target height off seabed from acoustic shadow (m)")
    area_sq_m: float = Field(..., description="Seabed contact footprint area (m²)")
    estimated_volume_m3: float = Field(..., description="Calculated 3D volumetric displacement (m³)")
    dry_mass_metric_tons: float = Field(..., description="Estimated dry structural mass in air (metric tons)")
    submerged_weight_kn: float = Field(..., description="Net underwater submerged weight (kN)")
    recommended_crane_lift_tons: float = Field(..., description="Required salvage crane hoist capacity (1.5x dynamic safety)")
    seabed_stability_index: float = Field(..., description="Friction holding force vs. current drag force ratio")
    seabed_mobility_status: str = Field(..., description="'Settled / Stable', 'Marginal / Scour Risk', or 'Unstable / Migrating Debris'")


class MasterTargetResult(BaseModel):
    detection_id: str = Field(..., description="Unique target identifier")
    class_id: int = Field(..., description="YOLO integer class ID")
    class_name: str = Field(..., description="Detected class (shipwreck, aircraft, fish, other)")
    display_name: str = Field(..., description="Human-friendly label")
    category: str = Field(..., description="Hazard category")
    bbox: BoundingBox = Field(..., description="Target bounding box in pixel and normalized coordinates")
    
    # Confidence & Fusion
    ai_confidence: float = Field(..., description="Raw neural network probability [0 - 1]")
    calibrated_confidence: float = Field(..., description="Multi-source fused confidence [0 - 1]")
    trust_tier: TrustTier = Field(..., description="Calibrated operational trust tier")
    explainability_notes: List[str] = Field(default_factory=list, description="Reasoning for confidence adjustment")
    
    # Physical & Acoustic Corroboration
    shadow_evidence: ShadowEvidence = Field(..., description="Acoustic shadow corroboration metrics")
    dimensions: MasterPhysicalDimensions = Field(..., description="Precision physical dimensions & salvage requirements")
    
    # Geodesy & Navigation
    coordinates: GeoCoordinates = Field(..., description="WGS84, DMS, and UTM real-world position")
    distance_from_sensor_m: float = Field(..., description="Slant / ground distance from sensor (m)")
    bearing_degrees: float = Field(..., description="True navigational bearing from sensor (0 - 360°)")
    
    # Maritime Risk & Safety Directives
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Composite maritime hazard score [0 - 100]")
    risk_tier: RiskTier = Field(..., description="Categorical hazard level")
    color_hex: str = Field(..., description="UI badge color hex code")
    clearance: NavigationalClearance = Field(..., description="Water clearance and vessel draft vulnerabilities")
    action_recommendations: List[ActionRecommendation] = Field(default_factory=list, description="USCG/IMO/IHO directives")


class ExecutiveSummary(BaseModel):
    total_targets_detected: int = Field(..., description="Total targets identified in scan")
    verified_targets: int = Field(..., description="Targets confirmed with high confidence & shadow evidence")
    probable_debris: int = Field(..., description="Probable debris targets")
    ambiguous_anomalies: int = Field(..., description="Ambiguous seabed anomalies")
    suspected_false_alarms: int = Field(..., description="Filtered potential false alarms")
    class_breakdown: Dict[str, int] = Field(default_factory=dict, description="Counts per class")
    risk_tier_breakdown: Dict[str, int] = Field(default_factory=dict, description="Counts per hazard severity")
    immediate_notmar_required: bool = Field(..., description="True if any target poses shallow collision threat")
    max_hazard_score: float = Field(..., description="Peak maritime hazard score in survey")
    primary_alert_message: str = Field(..., description="High-level operational advisory summary")


class MasterAnalysisResult(BaseModel):
    status: str = Field("success", description="Pipeline execution status")
    mission_id: str = Field(..., description="Unique mission analysis identifier")
    image_metadata: ImageMetadata = Field(..., description="Image resolution, channels, and format")
    quality_assessment: QualityAssessment = Field(..., description="Acoustic image quality analysis")
    timings: StageTimings = Field(..., description="Execution duration across all 12 pipeline stages")
    targets: List[MasterTargetResult] = Field(default_factory=list, description="Synthesized target intelligence")
    geojson: GeoJSONFeatureCollection = Field(..., description="RFC 7946 GeoJSON FeatureCollection for mapping")
    summary: ExecutiveSummary = Field(..., description="Executive mission summary")
    annotated_image_base64: Optional[str] = Field(None, description="Base64 encoded visual overlay with boxes & shadows")
