"""
Pydantic schemas for the Master Analysis Pipeline.
Unifies all 12 stages: Input validation, quality checking, preprocessing,
YOLO detection/segmentation, candidate list, acoustic shadow evidence,
physics validation, confidence fusion, geolocation, dimension estimation,
risk classification, and final executive results.
"""

from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.detection import BoundingBox, ImageMetadata
from app.schemas.confidence import TrustTier
from app.schemas.risk import RiskTier, NavigationalClearance, ActionRecommendation
from app.schemas.geolocation import GeoCoordinates, GeoJSONFeatureCollection
from app.schemas.sonar import SonarNavigation, SonarTargetGeoreference


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
    # Pixel extents in raster / image
    pixel_width: float = Field(..., description="Target bounding box width in pixels")
    pixel_height: float = Field(..., description="Target bounding box height in pixels")
    
    # Real-world metric dimensions
    across_track_m: Optional[float] = Field(None, description="Physical extent across-track in meters")
    along_track_m: Optional[float] = Field(None, description="Physical extent along-track in meters")
    slant_range_m: Optional[float] = Field(None, description="Recorded or computed slant range in meters")
    ground_range_m: Optional[float] = Field(None, description="Projected ground range on seabed in meters")
    
    # Standard 3D dimensions & displacement
    length_m: Optional[float] = Field(None, description="Target along-track / maximum physical length (m)")
    width_m: Optional[float] = Field(None, description="Target across-track physical width (m)")
    height_m: Optional[float] = Field(None, description="Target height off seabed from acoustic shadow (m)")
    area_sq_m: Optional[float] = Field(None, description="Seabed contact footprint area (m²)")
    estimated_volume_m3: Optional[float] = Field(None, description="Calculated 3D volumetric displacement (m³)")
    
    # Salvage & Hydrodynamic stability
    dry_mass_metric_tons: Optional[float] = Field(None, description="Estimated dry structural mass in air (metric tons)")
    submerged_weight_kn: Optional[float] = Field(None, description="Net underwater submerged weight (kN)")
    recommended_crane_lift_tons: Optional[float] = Field(None, description="Required salvage crane hoist capacity (1.5x dynamic safety)")
    seabed_stability_index: Optional[float] = Field(None, description="Friction holding force vs. current drag force ratio")
    seabed_mobility_status: Optional[str] = Field(None, description="'Settled / Stable', 'Marginal / Scour Risk', or 'Unstable / Migrating Debris'")
    
    # Metadata & Quality
    measurement_method: str = Field(..., description="Method: 'sonar_raster_geometry', 'optical_camera_gsd', 'shadow_derived', etc.")
    measurement_status: str = Field(..., description="'verified_complete', 'partial_across_only', 'unavailable_missing_gsd'")
    warnings: List[str] = Field(default_factory=list, description="Measurement caveats, missing track data, or assumptions")


# Alias for cross-service consistency
TargetDimensions = MasterPhysicalDimensions


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
    coordinates: Optional[GeoCoordinates] = Field(None, description="WGS84, DMS, and UTM real-world position")
    distance_from_sensor_m: Optional[float] = Field(None, description="Slant / ground distance from sensor (m)")
    bearing_degrees: Optional[float] = Field(None, description="True navigational bearing from sensor (0 - 360°)")
    georeference: Optional[SonarTargetGeoreference] = Field(
        None, description="Sonar ping-track geospatial correlation and positioning telemetry"
    )
    
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


class SonarMetadataContext(BaseModel):
    """
    Provenance and acoustic metadata for raw sonar streams (.xtf, .jsf)
    propagated through the Master Analysis Pipeline.
    """
    format: str = Field(..., description="Raw sonar format ('XTF' or 'JSF')")
    filename: Optional[str] = Field(None, description="Original raw sonar filename")
    total_pings: int = Field(..., ge=0, description="Total pings in raw recording")
    channel_count: int = Field(..., ge=0, description="Total acoustic channels present")
    channels_included: List[int] = Field(default_factory=list, description="Channels rendered in waterfall raster")
    waterfall_width: int = Field(..., ge=0, description="Raster width in range bins")
    waterfall_height: int = Field(..., ge=0, description="Raster height in pings")
    channel_layout: str = Field(..., description="Acoustic channel arrangement")
    nadir_pixel_x: Optional[float] = Field(None, description="Ground-track nadir pixel column")
    meters_per_pixel: Optional[float] = Field(None, description="Calculated spatial resolution (m/pixel)")
    slant_range_m: Optional[float] = Field(None, description="Recorded slant range in meters")
    navigation: Optional[SonarNavigation] = Field(None, description="Representative navigation fix")
    warnings: List[str] = Field(default_factory=list, description="Ingestion and parser warnings")
    artifact_id: Optional[str] = Field(None, description="Unique waterfall raster artifact identifier")
    raster_reference: Optional[str] = Field(None, description="API retrieval route for the stable waterfall raster")
    raster_path: Optional[str] = Field(None, description="Local filesystem path to the waterfall raster artifact")
    track_artifact_id: Optional[str] = Field(None, description="Unique navigation track artifact identifier")
    track_reference: Optional[str] = Field(None, description="API retrieval route for the ordered navigation track")


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
    prediction_image_path: Optional[str] = Field(None, description="Backend path of the persisted prediction image")
    prediction_image_url: Optional[str] = Field(None, description="Cloudinary HTTPS URL when configured")
    sonar_metadata: Optional[SonarMetadataContext] = Field(None, description="Raw sonar provenance and acoustic context if ingested from .xtf or .jsf")


class AnalysisSourceInfo(BaseModel):
    """
    Provenance of the ingested sonar or imagery data.
    """
    model_config = ConfigDict(extra="ignore")

    filename: Optional[str] = Field(None, description="Original filename of the ingested recording or image")
    format: str = Field(..., description="File format identifier ('XTF', 'JSF', 'PNG', 'JPEG', 'TIFF', etc.)")
    file_size: Optional[int] = Field(None, ge=0, description="Size of the uploaded file in bytes")
    file_size_bytes: Optional[int] = Field(None, ge=0, description="Size of the uploaded file in bytes (alias)")


class SonarRasterMetadata(BaseModel):
    """
    Acoustic raster and acquisition geometry metadata generated by the sonar ingestion pipeline.
    """
    model_config = ConfigDict(extra="ignore")

    total_pings: Optional[int] = Field(None, ge=0, description="Total pings in raw recording")
    channel_count: Optional[int] = Field(None, ge=0, description="Total acoustic channels present")
    selected_channels: List[int] = Field(default_factory=list, description="Channels rendered in waterfall raster")
    channel_layout: Optional[str] = Field(None, description="Acoustic channel arrangement (e.g., 'port_starboard')")
    waterfall_width: Optional[int] = Field(None, ge=0, description="Raster width across-track in pixels")
    waterfall_height: Optional[int] = Field(None, ge=0, description="Raster height along-track in pings/lines")
    nadir_pixel: Optional[float] = Field(None, description="Across-track ground-track nadir pixel column")
    meters_per_pixel: Optional[float] = Field(None, description="Spatial resolution in meters/pixel")
    slant_range_m: Optional[float] = Field(None, description="Recorded slant range in meters")
    artifact_id: Optional[str] = Field(None, description="Unique artifact identifier for the waterfall raster")
    raster_reference: Optional[str] = Field("/api/v1/sonar/raster", description="API endpoint reference to retrieve waterfall raster binary")
    track_artifact_id: Optional[str] = Field(None, description="Unique artifact identifier for the navigation track")
    track_reference: Optional[str] = Field(None, description="API endpoint reference to retrieve navigation track")
    coordinate_convention: str = Field(
        "top_left_origin_x_across_y_along",
        description="Origin (0,0) is top-left. X: across-track [0, width-1]. Y: along-track ping index [0, height-1]."
    )


class SonarAnalysisResponse(BaseModel):
    """
    Unified Sonar Analysis response contract for MarineScan.
    Aggregates source provenance, raw sonar/raster metadata, navigation fix,
    the complete 12-stage analysis result, and pipeline warnings.
    Provides top-level backward-compatible fields matching MasterAnalysisResult.
    """
    model_config = ConfigDict(extra="ignore")

    status: str = Field("success", description="Pipeline execution status")
    source: AnalysisSourceInfo = Field(..., description="Ingested file provenance")
    sonar: Optional[SonarRasterMetadata] = Field(None, description="Acoustic raster metadata if ingested from raw sonar (.xtf, .jsf)")
    navigation: Optional[SonarNavigation] = Field(None, description="Representative navigation fix if available from sonar telemetry")
    analysis: MasterAnalysisResult = Field(..., description="Authoritative 12-stage intelligence analysis results")
    warnings: List[str] = Field(default_factory=list, description="Ingestion and analysis warnings")

    # Backward-compatibility fields directly matching MasterAnalysisResult:
    mission_id: Optional[str] = Field(None, description="Unique mission analysis identifier")
    targets: List[MasterTargetResult] = Field(default_factory=list, description="Synthesized target intelligence")
    summary: Optional[ExecutiveSummary] = Field(None, description="Executive mission summary")
    timings: Optional[StageTimings] = Field(None, description="Execution duration across all 12 pipeline stages")
    geojson: Optional[GeoJSONFeatureCollection] = Field(None, description="RFC 7946 GeoJSON FeatureCollection for mapping")
    quality_assessment: Optional[QualityAssessment] = Field(None, description="Acoustic image quality analysis")
    image_metadata: Optional[ImageMetadata] = Field(None, description="Image resolution, channels, and format")
    sonar_metadata: Optional[SonarMetadataContext] = Field(None, description="Raw sonar provenance context")

    @classmethod
    def from_analysis_result(
        cls,
        result: MasterAnalysisResult,
        filename: Optional[str] = None,
        file_size_bytes: Optional[int] = None,
    ) -> "SonarAnalysisResponse":
        """
        Factory to wrap a MasterAnalysisResult into the unified SonarAnalysisResponse contract.
        Handles both raw sonar recordings (.xtf, .jsf) and standard image uploads (.png, .jpg, etc.).
        """
        sonar_ctx = result.sonar_metadata
        if sonar_ctx is not None:
            # Raw sonar format (.xtf, .jsf)
            src_format = sonar_ctx.format
            src_filename = filename or sonar_ctx.filename
            raster_ref = (
                sonar_ctx.raster_reference
                or f"/api/v1/analyses/{result.mission_id}/sonar/raster"
            )
            art_id = sonar_ctx.artifact_id or f"art_{result.mission_id}"
            track_ref = (
                sonar_ctx.track_reference
                or f"/api/v1/analyses/{result.mission_id}/sonar/track"
            )
            track_art_id = sonar_ctx.track_artifact_id or f"track_{result.mission_id}"
            sonar_meta = SonarRasterMetadata(
                artifact_id=art_id,
                total_pings=sonar_ctx.total_pings,
                channel_count=sonar_ctx.channel_count,
                selected_channels=sonar_ctx.channels_included,
                channel_layout=sonar_ctx.channel_layout,
                waterfall_width=sonar_ctx.waterfall_width,
                waterfall_height=sonar_ctx.waterfall_height,
                nadir_pixel=sonar_ctx.nadir_pixel_x,
                meters_per_pixel=sonar_ctx.meters_per_pixel,
                slant_range_m=sonar_ctx.slant_range_m,
                raster_reference=raster_ref,
                track_artifact_id=track_art_id,
                track_reference=track_ref,
                coordinate_convention="top_left_origin_x_across_y_along",
            )
            nav = sonar_ctx.navigation
            if nav is not None:
                has_any_nav = any([
                    nav.latitude is not None,
                    nav.longitude is not None,
                    nav.heading_deg is not None,
                    nav.altitude_m is not None,
                    nav.depth_m is not None,
                ])
                if not has_any_nav:
                    nav = None
            warnings = list(sonar_ctx.warnings)
        else:
            # Standard image upload (.png, .jpg, etc.)
            src_format = result.image_metadata.format or "IMAGE"
            src_filename = filename
            sonar_meta = None
            nav = None
            warnings = []

        source_info = AnalysisSourceInfo(
            filename=src_filename,
            format=src_format,
            file_size=file_size_bytes,
            file_size_bytes=file_size_bytes,
        )

        return cls(
            status=result.status,
            source=source_info,
            sonar=sonar_meta,
            navigation=nav,
            analysis=result,
            warnings=warnings,
            # Top-level backward compatibility fields:
            mission_id=result.mission_id,
            targets=result.targets,
            summary=result.summary,
            timings=result.timings,
            geojson=result.geojson,
            quality_assessment=result.quality_assessment,
            image_metadata=result.image_metadata,
            sonar_metadata=result.sonar_metadata,
        )

