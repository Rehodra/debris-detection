"""
Physics and Hydrography Service for MarineScan.
Synthesizes AI detections, acoustic shadow evidence, and sonar geometry to compute:
- Ocean acoustic parameters (sound speed, absorption, wavelength)
- Slant-to-ground range corrections & grazing angles
- 3D volume, mass, buoyancy, and salvage crane lift ratings
- Hydrodynamic seabed stability under ocean currents
- Physical plausibility and engineering verification
"""

import math
import logging
from typing import Optional, List, Dict, Any, Tuple

from app.schemas.physics import (
    SedimentType,
    OceanEnvironmentParams,
    AcousticEnvironment,
    SonarGeometry,
    ObjectPhysicalProperties,
    HydrodynamicStability,
    PhysicalPlausibility,
    TargetPhysicsAnalysis,
    BatchPhysicsResponse,
)
from app.schemas.detection import DetectionItem, BoundingBox
from app.schemas.shadow import ShadowAnalysisResult

logger = logging.getLogger("marinescan.services.physics")

GRAVITY = 9.80665  # m/s^2
DEFAULT_SEAWATER_DENSITY = 1025.0  # kg/m^3

# Class-specific shape compaction factors, bulk densities, drag coefficients, and aspect models
CLASS_PHYSICAL_MODELS = {
    "shipwreck": {
        "compaction_factor": 0.65,
        "density_kg_m3": 1800.0,
        "drag_coeff": 1.15,
        "default_height_ratio": 0.45,
        "min_length_m": 3.0,
        "max_length_m": 350.0,
        "min_width_m": 1.0,
        "max_width_m": 50.0,
        "max_height_m": 35.0,
    },
    "pipe": {
        "compaction_factor": 0.70,
        "density_kg_m3": 7850.0,  # Steel / heavy pipeline
        "drag_coeff": 0.85,
        "default_height_ratio": 0.20,
        "min_length_m": 0.5,
        "max_length_m": 300.0,
        "min_width_m": 0.1,
        "max_width_m": 6.0,
        "max_height_m": 6.0,
    },
    "ghost_net": {
        "compaction_factor": 0.25,
        "density_kg_m3": 1150.0,  # Synthetic fishing gear polymers in brine
        "drag_coeff": 1.45,
        "default_height_ratio": 0.35,
        "min_length_m": 0.5,
        "max_length_m": 200.0,
        "min_width_m": 0.5,
        "max_width_m": 100.0,
        "max_height_m": 15.0,
    },
    "marine_debris": {
        "compaction_factor": 0.50,
        "density_kg_m3": 1350.0,  # Mixed plastic, metal drums, container fragments
        "drag_coeff": 1.05,
        "default_height_ratio": 0.40,
        "min_length_m": 0.2,
        "max_length_m": 50.0,
        "min_width_m": 0.2,
        "max_width_m": 25.0,
        "max_height_m": 15.0,
    },
    "aircraft": {
        "compaction_factor": 0.35,
        "density_kg_m3": 650.0,
        "drag_coeff": 0.85,
        "default_height_ratio": 0.30,
        "min_length_m": 2.0,
        "max_length_m": 85.0,
        "min_width_m": 2.0,
        "max_width_m": 80.0,
        "max_height_m": 20.0,
    },
    "fish": {
        "compaction_factor": 0.48,
        "density_kg_m3": 1025.0,  # Neutrally buoyant
        "drag_coeff": 0.25,
        "default_height_ratio": 0.35,
        "min_length_m": 0.05,
        "max_length_m": 18.0,
        "min_width_m": 0.02,
        "max_width_m": 6.0,
        "max_height_m": 6.0,
    },
    "other": {
        "compaction_factor": 0.50,
        "density_kg_m3": 1400.0,
        "drag_coeff": 1.05,
        "default_height_ratio": 0.40,
        "min_length_m": 0.15,
        "max_length_m": 60.0,
        "min_width_m": 0.15,
        "max_width_m": 30.0,
        "max_height_m": 15.0,
    },
    # Real project classes (ours_ghostnet_pipe_debris.pt) — added alongside the
    # legacy entries above rather than replacing them, since existing tests
    # exercise the legacy class names directly.
    "ghost_net": {
        "compaction_factor": 0.15,   # porous mesh, mostly open space in its bounding box
        "density_kg_m3": 1050.0,     # waterlogged nylon/polypropylene netting, slightly denser than seawater
        "drag_coeff": 1.30,          # open mesh catches significant current flow
        "default_height_ratio": 0.12,  # lies flat on the seabed unless snagged into a mound
        "min_length_m": 0.5,
        "max_length_m": 150.0,       # large derelict net masses can span many meters
        "min_width_m": 0.3,
        "max_width_m": 60.0,
        "max_height_m": 4.0,
    },
    "pipe": {
        "compaction_factor": 0.78,   # circular cylinder cross-section (~pi/4 of bounding box)
        "density_kg_m3": 2200.0,     # steel / concrete-coated subsea pipeline
        "drag_coeff": 1.20,          # cylinder in crossflow
        "default_height_ratio": 0.90,  # height approx equals width (circular cross-section)
        "min_length_m": 2.0,
        "max_length_m": 500.0,       # pipeline segments can run very long
        "min_width_m": 0.1,
        "max_width_m": 2.5,
        "max_height_m": 2.5,
    },
    "marine_debris": {
        "compaction_factor": 0.50,
        "density_kg_m3": 1400.0,
        "drag_coeff": 1.05,
        "default_height_ratio": 0.40,
        "min_length_m": 0.15,
        "max_length_m": 60.0,
        "min_width_m": 0.15,
        "max_width_m": 30.0,
        "max_height_m": 15.0,
    },
}

SEDIMENT_FRICTION_MAP = {
    SedimentType.FINE_SAND: 0.45,
    SedimentType.COARSE_SAND: 0.55,
    SedimentType.MUD_SILT: 0.35,
    SedimentType.GRAVEL_PEBBLE: 0.65,
    SedimentType.ROCK_REEF: 0.80,
}


class PhysicsService:
    """Production physics, acoustics, and hydrography engine for underwater debris analytics."""

    # -------------------------------------------------------------------------
    # 1. Ocean Acoustic Environment (Mackenzie 1981 & Absorption)
    # -------------------------------------------------------------------------

    def calculate_sound_speed(
        self,
        temperature_c: float = 12.0,
        salinity_ppt: float = 35.0,
        depth_m: float = 30.0,
    ) -> float:
        """
        Calculate sound speed (m/s) in seawater via the Mackenzie (1981) formulation.
        Valid for: Temp 2 - 30 deg C, Salinity 25 - 40 ppt, Depth 0 - 8000 m.
        """
        t = float(temperature_c)
        s = float(salinity_ppt)
        d = float(depth_m)

        c = (
            1448.96
            + 4.591 * t
            - 5.304e-2 * (t ** 2)
            + 2.374e-4 * (t ** 3)
            + 1.340 * (s - 35.0)
            + 1.630e-2 * d
            + 1.675e-7 * (d ** 2)
            - 1.025e-2 * t * (s - 35.0)
            - 7.139e-13 * t * (d ** 3)
        )
        return round(float(c), 2)

    def calculate_acoustic_absorption(
        self,
        frequency_khz: float = 450.0,
        temperature_c: float = 12.0,
        salinity_ppt: float = 35.0,
        depth_m: float = 30.0,
    ) -> float:
        """
        Estimate acoustic absorption coefficient in seawater (dB/km).
        """
        f = max(1.0, float(frequency_khz))
        f2 = f ** 2
        # Francois-Garrison / Schulkin-Marsh empirical model for coastal waters
        alpha = 0.0033 + 0.11 * (f2 / (1.0 + f2)) + 44.0 * (f2 / (4100.0 + f2)) + 3.0e-4 * f2
        return round(float(alpha), 2)

    def get_acoustic_environment(
        self,
        params: Optional[OceanEnvironmentParams] = None,
    ) -> AcousticEnvironment:
        """Compute complete acoustic environment properties."""
        p = params or OceanEnvironmentParams()
        speed = self.calculate_sound_speed(p.temperature_c, p.salinity_ppt, p.depth_m)
        freq_khz = p.sonar_frequency_khz or 450.0
        absorption = self.calculate_acoustic_absorption(freq_khz, p.temperature_c, p.salinity_ppt, p.depth_m)

        # Wavelength lambda = c / f
        freq_hz = freq_khz * 1000.0
        wavelength_m = speed / freq_hz
        wavelength_mm = round(wavelength_m * 1000.0, 3)

        return AcousticEnvironment(
            sound_speed_mps=speed,
            absorption_db_per_km=absorption,
            acoustic_wavelength_mm=wavelength_mm,
            water_density_kg_per_m3=DEFAULT_SEAWATER_DENSITY,
        )

    # -------------------------------------------------------------------------
    # 2. Sonar Geometry & Slant Range Ground Correction
    # -------------------------------------------------------------------------

    def calculate_sonar_geometry(
        self,
        sensor_altitude_m: float,
        slant_range_m: float,
    ) -> SonarGeometry:
        """
        Convert slant range to true seafloor ground range and compute acoustic grazing angle.
        """
        alt = max(0.1, float(sensor_altitude_m))
        sr = max(alt, float(slant_range_m))

        ground_range = math.sqrt(max(0.0, (sr ** 2) - (alt ** 2)))
        sin_grazing = min(1.0, max(0.0, alt / sr))
        grazing_deg = math.degrees(math.asin(sin_grazing))

        return SonarGeometry(
            sensor_altitude_m=round(alt, 2),
            slant_range_m=round(sr, 2),
            ground_range_m=round(ground_range, 2),
            grazing_angle_degrees=round(grazing_deg, 2),
        )

    # -------------------------------------------------------------------------
    # 3. 3D Volume, Mass, Buoyancy & Salvage Capacity
    # -------------------------------------------------------------------------

    def estimate_3d_properties(
        self,
        class_name: str,
        length_m: float,
        width_m: float,
        height_m: Optional[float] = None,
        shadow_height_m: Optional[float] = None,
    ) -> ObjectPhysicalProperties:
        """
        Estimate 3D volume, material mass, Archimedes buoyant force, submerged weight,
        and required salvage crane lift capacity.
        """
        c_lower = class_name.lower()
        model = CLASS_PHYSICAL_MODELS.get(c_lower, CLASS_PHYSICAL_MODELS["other"])

        l = max(0.05, float(length_m))
        w = max(0.02, float(width_m))

        if shadow_height_m is not None and shadow_height_m > 0.0:
            h = float(shadow_height_m)
            h_src = "shadow_derived"
        elif height_m is not None and height_m > 0.0:
            h = float(height_m)
            h_src = "user_provided"
        else:
            h = round(min(l, w) * model["default_height_ratio"], 2)
            h = max(0.02, h)
            h_src = "aspect_modeled"

        # 3D Volume
        compaction = model["compaction_factor"]
        volume_m3 = round(l * w * h * compaction, 3)

        # Mass and Gravitational Weights
        density = model["density_kg_m3"]
        dry_mass_kg = volume_m3 * density
        dry_mass_tons = round(dry_mass_kg / 1000.0, 3)

        # Archimedes Buoyant Force: F_B = rho_water * V * g
        buoyant_force_n = DEFAULT_SEAWATER_DENSITY * volume_m3 * GRAVITY
        buoyant_force_kn = round(buoyant_force_n / 1000.0, 3)

        # Dry Weight in kN
        dry_weight_kn = (dry_mass_kg * GRAVITY) / 1000.0

        # Submerged Weight (apparent weight in water)
        submerged_weight_kn = round(max(0.0, dry_weight_kn - buoyant_force_kn), 3)

        # Submerged Mass in metric tons
        submerged_mass_tons = round((submerged_weight_kn * 1000.0) / (GRAVITY * 1000.0), 3)

        # Recommended crane hoist capacity with 1.5x dynamic safety factor
        crane_lift_tons = round(max(0.1, submerged_mass_tons * 1.5), 2)

        return ObjectPhysicalProperties(
            length_m=round(l, 2),
            width_m=round(w, 2),
            height_m=round(h, 2),
            height_source=h_src,
            estimated_volume_m3=volume_m3,
            material_density_kg_m3=density,
            dry_mass_metric_tons=dry_mass_tons,
            buoyant_force_kn=buoyant_force_kn,
            submerged_weight_kn=submerged_weight_kn,
            submerged_mass_metric_tons=submerged_mass_tons,
            recommended_crane_lift_tons=crane_lift_tons,
        )

    # -------------------------------------------------------------------------
    # 4. Hydrodynamic Seabed Stability Assessment
    # -------------------------------------------------------------------------

    def assess_hydrodynamic_stability(
        self,
        class_name: str,
        width_m: float,
        height_m: float,
        submerged_weight_kn: float,
        bottom_current_mps: float = 0.75,
        sediment_type: SedimentType = SedimentType.FINE_SAND,
    ) -> HydrodynamicStability:
        """
        Evaluate hydrodynamic frontal drag versus seabed friction holding force.
        Determines whether debris will remain anchored or migrate as a navigational hazard.
        """
        c_lower = class_name.lower()
        model = CLASS_PHYSICAL_MODELS.get(c_lower, CLASS_PHYSICAL_MODELS["other"])

        # Frontal projected area A = width * height
        frontal_area = max(0.01, width_m * height_m)
        cd = model["drag_coeff"]
        u = max(0.01, float(bottom_current_mps))

        # Hydrodynamic Drag Force: F_D = 0.5 * rho * C_d * A * U^2
        drag_force_n = 0.5 * DEFAULT_SEAWATER_DENSITY * cd * frontal_area * (u ** 2)
        drag_force_kn = round(drag_force_n / 1000.0, 3)

        # Seabed friction holding force: F_f = mu * W_submerged
        mu = SEDIMENT_FRICTION_MAP.get(sediment_type, 0.45)
        holding_force_kn = round(mu * max(0.0, submerged_weight_kn), 3)

        # Stability index S = F_f / F_D
        if drag_force_kn <= 0.0001:
            stability_index = 999.0
        else:
            stability_index = round(holding_force_kn / drag_force_kn, 2)

        # Mobility Classification
        if c_lower == "fish":
            mobility = "Mobile Organism"
        elif stability_index >= 1.5:
            mobility = "Settled / Stable in Sediment"
        elif stability_index >= 1.0:
            mobility = "Marginal Stability / Risk of Scour"
        else:
            mobility = "Unstable / Migrating Debris Hazard"

        return HydrodynamicStability(
            frontal_area_m2=round(frontal_area, 2),
            drag_coefficient=cd,
            current_velocity_mps=round(u, 2),
            current_drag_force_kn=drag_force_kn,
            sediment_friction_coefficient=mu,
            sediment_holding_force_kn=holding_force_kn,
            stability_index=stability_index,
            mobility_status=mobility,
        )

    # -------------------------------------------------------------------------
    # 5. Physical Plausibility & Verification
    # -------------------------------------------------------------------------

    def verify_physical_plausibility(
        self,
        class_name: str,
        length_m: float,
        width_m: float,
        height_m: float,
        has_shadow_evidence: bool = False,
    ) -> PhysicalPlausibility:
        """
        Verify whether dimensions conform to maritime engineering physics.
        Flags scale anomalies (e.g. 500m aircraft or 20cm shipwreck).
        """
        c_lower = class_name.lower()
        model = CLASS_PHYSICAL_MODELS.get(c_lower, CLASS_PHYSICAL_MODELS["other"])

        notes: List[str] = []
        is_plausible = True
        penalty = 0.0

        min_l, max_l = model["min_length_m"], model["max_length_m"]
        min_w, max_w = model["min_width_m"], model["max_width_m"]
        max_h = model["max_height_m"]

        if length_m < min_l:
            is_plausible = False
            penalty += 0.25
            notes.append(f"Length ({length_m:.1f}m) below expected minimum ({min_l}m) for {class_name}.")
        elif length_m > max_l:
            is_plausible = False
            penalty += 0.35
            notes.append(f"Length ({length_m:.1f}m) exceeds realistic maximum ({max_l}m) for {class_name}.")

        if width_m > max_w:
            is_plausible = False
            penalty += 0.25
            notes.append(f"Width ({width_m:.1f}m) exceeds realistic beam limit ({max_w}m).")

        if height_m > max_h:
            is_plausible = False
            penalty += 0.20
            notes.append(f"Height ({height_m:.1f}m) exceeds plausible seafloor relief ({max_h}m).")

        # Bonus if physical acoustic shadow corroborates the height
        bonus = 0.15 if has_shadow_evidence else 0.0
        if has_shadow_evidence:
            notes.append("Acoustic shadow corroborates 3D vertical relief.")

        score = max(0.0, min(1.0, 0.85 - penalty + bonus))

        if not notes:
            notes.append(f"Dimensions and aspect ratio align with standard {class_name} maritime profile.")

        return PhysicalPlausibility(
            is_plausible=is_plausible,
            physical_validation_score=round(score, 3),
            plausibility_notes=notes,
        )

    # -------------------------------------------------------------------------
    # 6. Combined Synthesis: AI Detection + Shadow Evidence + Sonar Geometry
    # -------------------------------------------------------------------------

    def analyze_target_physics(
        self,
        detection_id: str,
        class_name: str,
        confidence: float,
        length_m: float,
        width_m: float,
        shadow_result: Optional[ShadowAnalysisResult] = None,
        env_params: Optional[OceanEnvironmentParams] = None,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> TargetPhysicsAnalysis:
        """
        Synthesize AI detection, shadow evidence, and sonar geometry into a complete physical analysis.
        """
        p = env_params or OceanEnvironmentParams()
        acoustic_env = self.get_acoustic_environment(p)

        # Sonar geometry if available
        geometry = None
        if sensor_altitude_m is not None and slant_range_m is not None:
            geometry = self.calculate_sonar_geometry(sensor_altitude_m, slant_range_m)

        # Extract shadow evidence
        has_shadow = False
        shadow_score = None
        shadow_h = None
        if shadow_result and shadow_result.has_shadow:
            has_shadow = True
            shadow_score = shadow_result.shadow_score
            if shadow_result.extent and shadow_result.extent.estimated_object_height_m:
                shadow_h = shadow_result.extent.estimated_object_height_m

        # 3D properties
        phys_props = self.estimate_3d_properties(
            class_name=class_name,
            length_m=length_m,
            width_m=width_m,
            shadow_height_m=shadow_h,
        )

        # Hydrodynamic stability
        stability = self.assess_hydrodynamic_stability(
            class_name=class_name,
            width_m=phys_props.width_m,
            height_m=phys_props.height_m,
            submerged_weight_kn=phys_props.submerged_weight_kn,
            bottom_current_mps=p.bottom_current_mps,
            sediment_type=p.sediment_type,
        )

        # Plausibility
        plausibility = self.verify_physical_plausibility(
            class_name=class_name,
            length_m=phys_props.length_m,
            width_m=phys_props.width_m,
            height_m=phys_props.height_m,
            has_shadow_evidence=has_shadow,
        )

        return TargetPhysicsAnalysis(
            detection_id=detection_id,
            class_name=class_name,
            confidence=round(confidence, 4),
            has_shadow_evidence=has_shadow,
            shadow_score=shadow_score,
            environment=acoustic_env,
            sonar_geometry=geometry,
            physical_properties=phys_props,
            hydrodynamic_stability=stability,
            plausibility=plausibility,
        )

    def enrich_detections_with_physics(
        self,
        detections: List[Dict[str, Any]],
        shadow_results: Optional[List[ShadowAnalysisResult]] = None,
        env_params: Optional[OceanEnvironmentParams] = None,
        meters_per_pixel: float = 0.05,
        sensor_altitude_m: Optional[float] = None,
        slant_range_m: Optional[float] = None,
    ) -> BatchPhysicsResponse:
        """
        Batch enrich multiple detections with physical metrics and stability ratings.
        """
        shadow_lookup = {r.detection_id: r for r in (shadow_results or [])}
        results: List[TargetPhysicsAnalysis] = []

        shadow_count = 0
        unstable_count = 0

        for det in detections:
            det_id = det.get("detection_id", "unknown")
            cname = det.get("class_name", "other")
            conf = float(det.get("confidence", 0.5))

            # Retrieve or calculate physical length and width
            phys_dim = det.get("physical_dimensions")
            if phys_dim and "length_meters" in phys_dim and "width_meters" in phys_dim:
                l_m = float(phys_dim["length_meters"])
                w_m = float(phys_dim["width_meters"])
            else:
                bbox = det.get("bbox", {})
                w_px = float(bbox.get("width", 50.0))
                h_px = float(bbox.get("height", 50.0))
                l_m = max(w_px, h_px) * meters_per_pixel
                w_m = min(w_px, h_px) * meters_per_pixel

            shadow_res = shadow_lookup.get(det_id)
            analysis = self.analyze_target_physics(
                detection_id=det_id,
                class_name=cname,
                confidence=conf,
                length_m=l_m,
                width_m=w_m,
                shadow_result=shadow_res,
                env_params=env_params,
                sensor_altitude_m=sensor_altitude_m,
                slant_range_m=slant_range_m,
            )
            results.append(analysis)

            if analysis.has_shadow_evidence:
                shadow_count += 1
            if "Unstable" in analysis.hydrodynamic_stability.mobility_status:
                unstable_count += 1

        return BatchPhysicsResponse(
            status="success",
            total_targets_analyzed=len(detections),
            targets_with_shadow_corroboration=shadow_count,
            unstable_hazards_detected=unstable_count,
            results=results,
        )


# Global service instance
physics_service = PhysicsService()
