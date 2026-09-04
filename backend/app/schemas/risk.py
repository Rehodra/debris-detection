"""
Pydantic schemas for Maritime Hazard, Navigational Safety, and Environmental Risk.
Models under-keel clearance, trawl entanglement, subsea infrastructure threats,
environmental pollution ratings, composite hazard scoring, and action directives.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    CRITICAL = "CRITICAL"   # 80 - 100: Immediate navigational / infrastructure / pollution emergency
    HIGH = "HIGH"           # 60 - 79: Significant hazard, NOTMAR recommended, trawl snag risk
    MODERATE = "MODERATE"   # 40 - 59: Navigational obstruction to deep-draft ships, charted warning
    LOW = "LOW"             # 0 - 39: Deep water, settled, negligible hazard


class NavigationalClearance(BaseModel):
    water_depth_m: float = Field(..., description="Total water column depth at target position (m)")
    object_height_m: float = Field(..., description="Target height off seabed (m)")
    clearance_m: float = Field(..., description="Clearance water column depth above top of object (m)")
    threatens_shallow_draft: bool = Field(..., description="True if clearance <= 3.5m (threat to fishing/tugs/pleasure craft)")
    threatens_medium_draft: bool = Field(..., description="True if clearance <= 7.5m (threat to coastal cargo/ferries)")
    threatens_deep_draft: bool = Field(..., description="True if clearance <= 15.0m (threat to container ships/tankers)")


class RiskFactors(BaseModel):
    navigational_risk: float = Field(..., ge=0.0, le=100.0, description="Collision & grounding risk score [0 - 100]")
    trawl_risk: float = Field(..., ge=0.0, le=100.0, description="Commercial fishing & net entanglement risk [0 - 100]")
    infrastructure_risk: float = Field(..., ge=0.0, le=100.0, description="Pipeline & subsea cable collision threat [0 - 100]")
    environmental_risk: float = Field(..., ge=0.0, le=100.0, description="Chemical, bunker fuel, or ghost net pollution threat [0 - 100]")
    mobility_risk: float = Field(..., ge=0.0, le=100.0, description="Seafloor migration & current drift risk [0 - 100]")


class ActionRecommendation(BaseModel):
    category: str = Field(..., description="'NAVIGATION', 'CHARTING', 'SALVAGE', or 'ENVIRONMENTAL'")
    priority: str = Field(..., description="'IMMEDIATE', 'HIGH', 'STANDARD', or 'ROUTINE'")
    action_text: str = Field(..., description="Prescribed operational directive")
    authority_standard: str = Field(..., description="Regulatory body/standard (e.g. 'IHO S-57', 'USCG / IMO NOTMAR')")


class TargetRiskAssessment(BaseModel):
    detection_id: str = Field(..., description="Debris target identifier")
    class_name: str = Field(..., description="Target class (shipwreck, aircraft, fish, other)")
    composite_risk_score: float = Field(..., ge=0.0, le=100.0, description="Composite maritime hazard score [0 - 100]")
    risk_tier: RiskTier = Field(..., description="Categorical risk classification")
    color_hex: str = Field(..., description="UI hex color code for risk badge")
    clearance: NavigationalClearance = Field(..., description="Water clearance and vessel draft vulnerability")
    factors: RiskFactors = Field(..., description="Individual hazard component breakdown")
    recommendations: List[ActionRecommendation] = Field(default_factory=list, description="Actionable directives")


class BatchRiskResponse(BaseModel):
    status: str = Field("success", description="Execution status")
    total_targets_assessed: int = Field(..., description="Total debris targets evaluated")
    critical_count: int = Field(..., description="Count of CRITICAL risk hazards")
    high_count: int = Field(..., description="Count of HIGH risk hazards")
    moderate_count: int = Field(..., description="Count of MODERATE risk hazards")
    low_count: int = Field(..., description="Count of LOW risk hazards")
    immediate_notmar_required: bool = Field(..., description="True if any target warrants emergency Notice to Mariners")
    results: List[TargetRiskAssessment] = Field(default_factory=list, description="Per-target risk profiles")
