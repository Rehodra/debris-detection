"""
Pydantic schemas for Marine Debris Physics, Hydrography, and Ocean Acoustics.
Models ocean environmental parameters, slant-to-ground range corrections,
3D volumetric & mass estimation, buoyant forces, salvage requirements,
and seabed hydrodynamic stability.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class SedimentType(str, Enum):
    FINE_SAND = "fine_sand"
    COARSE_SAND = "coarse_sand"
    MUD_SILT = "mud_silt"
    GRAVEL_PEBBLE = "gravel_pebble"
    ROCK_REEF = "rock_reef"


class OceanEnvironmentParams(BaseModel):
    temperature_c: float = Field(12.0, description="Water temperature in degrees Celsius")
    salinity_ppt: float = Field(35.0, ge=0.0, le=45.0, description="Salinity in parts per thousand (ppt/PSU)")
    depth_m: float = Field(30.0, ge=0.0, description="Water column depth in meters")
    bottom_current_mps: float = Field(0.75, ge=0.0, description="Seafloor bottom current velocity in meters/second")
    sediment_type: SedimentType = Field(SedimentType.FINE_SAND, description="Seabed sediment classification")
    sonar_frequency_khz: Optional[float] = Field(450.0, gt=0.0, description="Sonar operating frequency in kHz")


class AcousticEnvironment(BaseModel):
    sound_speed_mps: float = Field(..., description="Speed of sound in seawater (m/s) via Mackenzie equation")
    absorption_db_per_km: float = Field(..., description="Acoustic absorption coefficient in dB/km")
    acoustic_wavelength_mm: float = Field(..., description="Acoustic wavelength in millimeters")
    water_density_kg_per_m3: float = Field(1025.0, description="Seawater density in kg/m^3")


class SonarGeometry(BaseModel):
    sensor_altitude_m: float = Field(..., gt=0.0, description="Sonar vehicle altitude off seabed (m)")
    slant_range_m: float = Field(..., gt=0.0, description="Slant range distance from sonar to target (m)")
    ground_range_m: float = Field(..., description="True horizontal ground range distance on seabed (m)")
    grazing_angle_degrees: float = Field(..., description="Acoustic grazing angle with seabed in degrees")


class ObjectPhysicalProperties(BaseModel):
    length_m: float = Field(..., description="Physical length of debris in meters")
    width_m: float = Field(..., description="Physical width of debris in meters")
    height_m: float = Field(..., description="Physical height off seabed in meters (shadow-derived or modeled)")
    height_source: str = Field(..., description="Source of height: 'shadow_derived' or 'aspect_modeled'")
    estimated_volume_m3: float = Field(..., description="Estimated 3D volume in cubic meters")
    material_density_kg_m3: float = Field(..., description="Estimated bulk material density (kg/m^3)")
    dry_mass_metric_tons: float = Field(..., description="Estimated dry mass in metric tons")
    buoyant_force_kn: float = Field(..., description="Archimedes buoyant force in kilonewtons (kN)")
    submerged_weight_kn: float = Field(..., description="Net submerged weight in seawater in kilonewtons (kN)")
    submerged_mass_metric_tons: float = Field(..., description="Effective submerged mass in metric tons")
    recommended_crane_lift_tons: float = Field(..., description="Recommended minimum crane rating (1.5x safety factor)")


class HydrodynamicStability(BaseModel):
    frontal_area_m2: float = Field(..., description="Frontal projected area facing bottom current (m^2)")
    drag_coefficient: float = Field(..., description="Estimated hydrodynamic drag coefficient (Cd)")
    current_velocity_mps: float = Field(..., description="Seafloor bottom current speed (m/s)")
    current_drag_force_kn: float = Field(..., description="Hydrodynamic drag force pushing the debris (kN)")
    sediment_friction_coefficient: float = Field(..., description="Seabed friction coefficient (mu)")
    sediment_holding_force_kn: float = Field(..., description="Sediment friction resistance holding debris in place (kN)")
    stability_index: float = Field(..., description="Ratio of holding friction to drag force (F_f / F_D)")
    mobility_status: str = Field(..., description="'Settled / Stable', 'Marginal / Scour Risk', or 'Unstable / Migrating'")


class PhysicalPlausibility(BaseModel):
    is_plausible: bool = Field(..., description="Whether dimensions and mass conform to maritime engineering physics")
    physical_validation_score: float = Field(..., ge=0.0, le=1.0, description="Composite physical plausibility score")
    plausibility_notes: List[str] = Field(default_factory=list, description="Engineering observations / warnings")


class TargetPhysicsAnalysis(BaseModel):
    detection_id: str = Field(..., description="Identifier of the debris target")
    class_name: str = Field(..., description="Target class (aircraft, fish, other, shipwreck)")
    confidence: float = Field(..., description="AI detection confidence")
    has_shadow_evidence: bool = Field(..., description="Whether physical shadow corroboration was incorporated")
    shadow_score: Optional[float] = Field(None, description="Score from shadow analysis")
    environment: AcousticEnvironment = Field(..., description="Ocean acoustic context")
    sonar_geometry: Optional[SonarGeometry] = Field(None, description="Sonar geometric parameters if supplied")
    physical_properties: ObjectPhysicalProperties = Field(..., description="3D dimensions, volume, mass, and lift")
    hydrodynamic_stability: HydrodynamicStability = Field(..., description="Seabed current stability & drag analysis")
    plausibility: PhysicalPlausibility = Field(..., description="Physical verification of target")


class BatchPhysicsResponse(BaseModel):
    status: str = Field("success", description="Execution status")
    total_targets_analyzed: int = Field(..., description="Total targets evaluated")
    targets_with_shadow_corroboration: int = Field(..., description="Count with verified acoustic shadow")
    unstable_hazards_detected: int = Field(..., description="Count of targets subject to current migration")
    results: List[TargetPhysicsAnalysis] = Field(default_factory=list, description="Per-target physical profiles")
