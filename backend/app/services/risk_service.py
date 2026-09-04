"""
Risk and Maritime Safety Assessment Service for MarineScan.
Evaluates navigational draft clearance, trawl & fishing gear entanglement,
subsea infrastructure threats, environmental pollution risks, and composite hazard ratings.
"""

import logging
from typing import Optional, List, Dict, Any, Tuple

from app.schemas.risk import (
    RiskTier,
    NavigationalClearance,
    RiskFactors,
    ActionRecommendation,
    TargetRiskAssessment,
    BatchRiskResponse,
)
from app.schemas.detection import DetectionItem
from app.schemas.shadow import ShadowAnalysisResult
from app.schemas.physics import TargetPhysicsAnalysis
from app.schemas.confidence import TargetConfidenceProfile, TrustTier

logger = logging.getLogger("marinescan.services.risk")

# UI Risk Badge Colors
RISK_COLOR_MAP = {
    RiskTier.CRITICAL: "#E63946",  # Red
    RiskTier.HIGH: "#F4A261",      # Orange
    RiskTier.MODERATE: "#E9C46A",  # Amber/Yellow
    RiskTier.LOW: "#2A9D8F",       # Teal/Green
}


class RiskService:
    """Production maritime hazard evaluation and safety advisory engine."""

    # -------------------------------------------------------------------------
    # 1. Navigational Clearance Assessment
    # -------------------------------------------------------------------------

    def calculate_navigational_clearance(
        self,
        water_depth_m: float,
        object_height_m: float,
    ) -> Tuple[NavigationalClearance, float]:
        """
        Evaluate under-keel clearance and compute navigational collision risk [0 - 100].
        """
        depth = max(1.0, float(water_depth_m))
        h = max(0.1, float(object_height_m))
        clearance = max(0.0, depth - h)

        threatens_shallow = clearance <= 3.5   # Coastal/tugs/fishing craft
        threatens_medium = clearance <= 7.5    # Coastal cargo, ferries
        threatens_deep = clearance <= 15.0     # Container ships, deep tankers

        # Navigational Risk Scoring Curve [0 - 100]
        if clearance <= 3.5:
            # Extreme collision risk for virtually all marine traffic
            nav_risk = 100.0
        elif clearance <= 7.5:
            # High collision risk for medium & deep vessels
            fraction = (7.5 - clearance) / 4.0
            nav_risk = 75.0 + (25.0 * fraction)
        elif clearance <= 15.0:
            # Threatens deep draft shipping lanes
            fraction = (15.0 - clearance) / 7.5
            nav_risk = 45.0 + (30.0 * fraction)
        elif clearance <= 30.0:
            # Safe for normal surface transit, minor concern in adverse seas
            fraction = (30.0 - clearance) / 15.0
            nav_risk = 15.0 + (30.0 * fraction)
        else:
            # Deep water obstruction
            fraction = max(0.0, (60.0 - clearance) / 30.0)
            nav_risk = 15.0 * fraction

        clearance_obj = NavigationalClearance(
            water_depth_m=round(depth, 2),
            object_height_m=round(h, 2),
            clearance_m=round(clearance, 2),
            threatens_shallow_draft=threatens_shallow,
            threatens_medium_draft=threatens_medium,
            threatens_deep_draft=threatens_deep,
        )
        return clearance_obj, round(nav_risk, 1)

    # -------------------------------------------------------------------------
    # 2. Factor Risk Evaluators
    # -------------------------------------------------------------------------

    def evaluate_trawl_risk(
        self,
        class_name: str,
        object_height_m: float,
        length_m: float,
    ) -> float:
        """Evaluate commercial fishing net & trawl snag hazard [0 - 100]."""
        c = class_name.lower()
        if c == "fish":
            return 0.0

        if c == "shipwreck":
            base = 65.0
            if object_height_m >= 2.5:
                base += 20.0
            if length_m >= 20.0:
                base += 10.0
            return min(100.0, base)

        elif c == "aircraft":
            # Wings, stabilizers, and broken fuselage strongly snag bottom gear
            base = 60.0
            if length_m >= 10.0:
                base += 15.0
            return min(95.0, base)

        else:  # other
            base = 35.0
            if object_height_m >= 2.0:
                base += 20.0
            return min(80.0, base)

    def evaluate_infrastructure_risk(
        self,
        class_name: str,
        mobility_status: str,
        distance_to_cable_m: Optional[float] = None,
    ) -> float:
        """Evaluate threat to subsea pipelines, fiber cables, or wind farm infrastructure [0 - 100]."""
        c = class_name.lower()
        if c == "fish":
            return 0.0

        # Base infrastructure threat from mobility/scour
        if "Unstable" in mobility_status or "Migrating" in mobility_status:
            # Active migrating debris under bottom currents
            score = 75.0
        elif "Marginal" in mobility_status:
            score = 45.0
        else:
            score = 20.0

        # If explicit distance to pipeline/cable corridor is supplied
        if distance_to_cable_m is not None:
            if distance_to_cable_m <= 50.0:
                score = max(score, 95.0)
            elif distance_to_cable_m <= 200.0:
                score = max(score, 75.0)
            elif distance_to_cable_m <= 500.0:
                score = max(score, 50.0)

        return min(100.0, score)

    def evaluate_environmental_risk(
        self,
        class_name: str,
        volume_m3: float,
    ) -> float:
        """Evaluate chemical, bunker fuel, or synthetic polymer pollution threat [0 - 100]."""
        c = class_name.lower()
        if c == "fish":
            return 0.0

        if c == "shipwreck":
            # Trapped fuel oil, lubricants, toxic antifouling paint, heavy metals
            if volume_m3 >= 200.0:
                return 85.0
            elif volume_m3 >= 50.0:
                return 65.0
            else:
                return 45.0

        elif c == "aircraft":
            # Hydraulic fluid, fuel residues, lithium battery packs
            return 50.0

        else:  # other
            # Ghost nets, plastics, containers
            return 35.0

    def evaluate_mobility_risk(
        self,
        stability_index: Optional[float],
        mobility_status: str,
    ) -> float:
        """Evaluate current drift and seafloor mobility threat [0 - 100]."""
        if "Unstable" in mobility_status or "Migrating" in mobility_status:
            return 90.0
        elif "Marginal" in mobility_status:
            return 55.0
        elif stability_index is not None and stability_index >= 5.0:
            return 5.0
        else:
            return 15.0

    # -------------------------------------------------------------------------
    # 3. Action Recommendations Generator
    # -------------------------------------------------------------------------

    def generate_recommendations(
        self,
        risk_tier: RiskTier,
        clearance: NavigationalClearance,
        factors: RiskFactors,
        class_name: str,
    ) -> List[ActionRecommendation]:
        """Generate standardized maritime action directives (NOTMAR, IHO, Salvage)."""
        recs: List[ActionRecommendation] = []
        c = class_name.lower()

        if c == "fish":
            recs.append(
                ActionRecommendation(
                    category="ENVIRONMENTAL",
                    priority="ROUTINE",
                    action_text="Natural marine biomass detected; no maritime navigation hazard.",
                    authority_standard="IHO S-57 / Marine Biology",
                )
            )
            return recs

        # 1. Navigational Collision Advisories
        if clearance.threatens_shallow_draft or factors.navigational_risk >= 80.0:
            recs.append(
                ActionRecommendation(
                    category="NAVIGATION",
                    priority="IMMEDIATE",
                    action_text="Broadcast urgent Notice to Mariners (NOTMAR) warning of shallow obstruction hazard.",
                    authority_standard="USCG / IMO NOTMAR Advisory",
                )
            )
            recs.append(
                ActionRecommendation(
                    category="CHARTING",
                    priority="HIGH",
                    action_text=f"Issue urgent S-57 Electronic Navigational Chart (ENC) update: chart obstruction with least depth {clearance.clearance_m}m.",
                    authority_standard="IHO S-57 / S-52 Standards",
                )
            )
        elif clearance.threatens_deep_draft:
            recs.append(
                ActionRecommendation(
                    category="NAVIGATION",
                    priority="HIGH",
                    action_text=f"Issue deep-draft vessel fairway advisory for obstruction with clearance depth {clearance.clearance_m}m.",
                    authority_standard="IMO Navigational Fairway Directive",
                )
            )

        # 2. Trawl & Fishing Gear Advisories
        if factors.trawl_risk >= 65.0:
            recs.append(
                ActionRecommendation(
                    category="NAVIGATION",
                    priority="HIGH",
                    action_text="Alert commercial fishing fleets of high snag/entanglement hazard for bottom trawl and drift nets.",
                    authority_standard="Fisheries & Maritime Safety Board",
                )
            )

        # 3. Subsea Infrastructure Stand-off
        if factors.infrastructure_risk >= 60.0:
            recs.append(
                ActionRecommendation(
                    category="SALVAGE",
                    priority="HIGH",
                    action_text="Establish a 250m subsea work and anchoring exclusion zone around proximate pipeline/cable corridor.",
                    authority_standard="Subsea Infrastructure Safety Code",
                )
            )

        # 4. Environmental & Salvage Survey
        if factors.environmental_risk >= 60.0:
            recs.append(
                ActionRecommendation(
                    category="ENVIRONMENTAL",
                    priority="STANDARD",
                    action_text="Deploy ROV inspection team for environmental survey to assess fuel containment and hull structural integrity.",
                    authority_standard="IMO Marine Environmental Protection Committee (MEPC)",
                )
            )

        # Fallback routine logging if low risk
        if not recs:
            recs.append(
                ActionRecommendation(
                    category="CHARTING",
                    priority="ROUTINE",
                    action_text="Log target in national hydrographic obstruction database; schedule inspection on next routine survey pass.",
                    authority_standard="IHO Hydrographic Survey Practice",
                )
            )

        return recs

    # -------------------------------------------------------------------------
    # 4. End-to-End Single Target Risk Assessment
    # -------------------------------------------------------------------------

    def assess_target_risk(
        self,
        detection_id: str,
        class_name: str,
        length_m: float,
        width_m: float,
        height_m: float,
        water_depth_m: float = 30.0,
        distance_to_cable_m: Optional[float] = None,
        physics_analysis: Optional[TargetPhysicsAnalysis] = None,
        confidence_profile: Optional[TargetConfidenceProfile] = None,
    ) -> TargetRiskAssessment:
        """
        Compute full multi-factor hazard assessment for a debris target.
        """
        c_lower = class_name.lower()

        # 1. Navigational Clearance
        clearance, nav_risk = self.calculate_navigational_clearance(water_depth_m, height_m)

        # 2. Trawl Snag Risk
        trawl_risk = self.evaluate_trawl_risk(class_name, height_m, length_m)

        # 3. Infrastructure Risk (integrating physics stability)
        mob_status = "Settled / Stable in Sediment"
        stab_idx = None
        vol_m3 = length_m * width_m * height_m * 0.5

        if physics_analysis:
            mob_status = physics_analysis.hydrodynamic_stability.mobility_status
            stab_idx = physics_analysis.hydrodynamic_stability.stability_index
            vol_m3 = physics_analysis.physical_properties.estimated_volume_m3

        infra_risk = self.evaluate_infrastructure_risk(class_name, mob_status, distance_to_cable_m)

        # 4. Environmental Risk
        env_risk = self.evaluate_environmental_risk(class_name, vol_m3)

        # 5. Mobility Risk
        mob_risk = self.evaluate_mobility_risk(stab_idx, mob_status)

        # Composite Multi-Factor Score [0 - 100]
        if c_lower == "fish":
            composite = 5.0
        else:
            composite = (
                0.35 * nav_risk +
                0.20 * trawl_risk +
                0.20 * infra_risk +
                0.15 * env_risk +
                0.10 * mob_risk
            )
            composite = max(0.0, min(100.0, composite))

        # Trust Tier Penalty: If confidence is suspected false alarm, attenuate risk
        if confidence_profile and confidence_profile.trust_tier == TrustTier.SUSPECTED_FALSE_ALARM:
            composite *= 0.65

        # Risk Tier Classification
        if composite >= 80.0:
            tier = RiskTier.CRITICAL
        elif composite >= 60.0:
            tier = RiskTier.HIGH
        elif composite >= 40.0:
            tier = RiskTier.MODERATE
        else:
            tier = RiskTier.LOW

        color = RISK_COLOR_MAP[tier]

        factors = RiskFactors(
            navigational_risk=round(nav_risk, 1),
            trawl_risk=round(trawl_risk, 1),
            infrastructure_risk=round(infra_risk, 1),
            environmental_risk=round(env_risk, 1),
            mobility_risk=round(mob_risk, 1),
        )

        recs = self.generate_recommendations(tier, clearance, factors, class_name)

        return TargetRiskAssessment(
            detection_id=detection_id,
            class_name=class_name,
            composite_risk_score=round(composite, 1),
            risk_tier=tier,
            color_hex=color,
            clearance=clearance,
            factors=factors,
            recommendations=recs,
        )

    # -------------------------------------------------------------------------
    # 5. Batch Risk Assessment across All Targets
    # -------------------------------------------------------------------------

    def assess_batch_risk(
        self,
        detections: List[Dict[str, Any]],
        water_depth_m: float = 30.0,
        physics_analyses: Optional[List[TargetPhysicsAnalysis]] = None,
        confidence_profiles: Optional[List[TargetConfidenceProfile]] = None,
        meters_per_pixel: float = 0.05,
    ) -> BatchRiskResponse:
        """
        Evaluate maritime hazard across all detections from an inspection mission.
        """
        phys_map = {p.detection_id: p for p in (physics_analyses or [])}
        conf_map = {c.detection_id: c for c in (confidence_profiles or [])}

        results: List[TargetRiskAssessment] = []
        counts = {RiskTier.CRITICAL: 0, RiskTier.HIGH: 0, RiskTier.MODERATE: 0, RiskTier.LOW: 0}
        immediate_notmar = False

        for det in detections:
            det_id = det.get("detection_id", "unknown")
            cname = det.get("class_name", "other")

            # Extract dimensions
            phys = phys_map.get(det_id)
            if phys:
                l_m = phys.physical_properties.length_m
                w_m = phys.physical_properties.width_m
                h_m = phys.physical_properties.height_m
            else:
                bbox = det.get("bbox", {})
                w_px = float(bbox.get("width", 50))
                h_px = float(bbox.get("height", 50))
                l_m = max(w_px, h_px) * meters_per_pixel
                w_m = min(w_px, h_px) * meters_per_pixel
                h_m = min(l_m, w_m) * 0.4

            conf_prof = conf_map.get(det_id)

            risk_assessment = self.assess_target_risk(
                detection_id=det_id,
                class_name=cname,
                length_m=l_m,
                width_m=w_m,
                height_m=h_m,
                water_depth_m=water_depth_m,
                physics_analysis=phys,
                confidence_profile=conf_prof,
            )
            results.append(risk_assessment)
            counts[risk_assessment.risk_tier] += 1

            if risk_assessment.risk_tier == RiskTier.CRITICAL or risk_assessment.clearance.threatens_shallow_draft:
                immediate_notmar = True

        return BatchRiskResponse(
            status="success",
            total_targets_assessed=len(detections),
            critical_count=counts[RiskTier.CRITICAL],
            high_count=counts[RiskTier.HIGH],
            moderate_count=counts[RiskTier.MODERATE],
            low_count=counts[RiskTier.LOW],
            immediate_notmar_required=immediate_notmar,
            results=results,
        )


# Global service instance
risk_service = RiskService()
