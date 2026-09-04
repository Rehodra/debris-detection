"""
Pydantic schemas for Acoustic Shadow Extraction and Analysis in Sonar Imagery.
Models candidate regions, spatial vectors, directional alignment, geometric extent,
and composite shadow scores.
"""

from typing import List, Tuple, Optional, Dict, Any
from pydantic import BaseModel, Field
from app.schemas.detection import BoundingBox


class ShadowCandidate(BaseModel):
    candidate_id: str = Field(..., description="Unique identifier for the shadow candidate")
    bbox: BoundingBox = Field(..., description="Bounding box enclosing the acoustic shadow")
    centroid: Tuple[float, float] = Field(..., description="Centroid (x, y) in pixel coordinates")
    contour_points: Optional[List[List[int]]] = Field(
        None, description="Simplified polygon contour coordinates [[x, y], ...]"
    )
    area_pixels: float = Field(..., description="Area of the segmented shadow in square pixels")
    mean_intensity: float = Field(..., description="Average acoustic backscatter intensity [0 - 255]")


class SpatialRelationship(BaseModel):
    highlight_centroid: Tuple[float, float] = Field(..., description="Centroid of detection highlight (x, y)")
    shadow_centroid: Tuple[float, float] = Field(..., description="Centroid of acoustic shadow (x, y)")
    offset_dx: float = Field(..., description="Horizontal displacement dx (shadow_x - highlight_x)")
    offset_dy: float = Field(..., description="Vertical displacement dy (shadow_y - highlight_y)")
    euclidean_distance_pixels: float = Field(..., description="Straight-line distance between centroids")
    boundary_gap_pixels: float = Field(..., description="Shortest distance between highlight and shadow box edges")
    is_adjacent: bool = Field(..., description="Whether shadow is directly adjacent to or touching the highlight")


class ShadowDirection(BaseModel):
    angle_degrees: float = Field(..., ge=0.0, le=360.0, description="Angle of shadow projection in degrees [0 - 360]")
    cardinal_direction: str = Field(..., description="Compass quadrant: E, SE, S, SW, W, NW, N, NE")
    expected_direction_degrees: Optional[float] = Field(
        None, description="Expected acoustic ray angle from transducer/nadir geometry"
    )
    direction_alignment_score: float = Field(
        1.0, ge=0.0, le=1.0, description="Consistency with acoustic propagation ray [0.0 - 1.0]"
    )


class ShadowExtent(BaseModel):
    length_pixels: float = Field(..., description="Shadow length measured along the acoustic projection ray")
    width_pixels: float = Field(..., description="Shadow width measured perpendicular to projection ray")
    aspect_ratio: float = Field(..., description="Ratio of shadow length to width")
    area_pixels: float = Field(..., description="Total shadow footprint in pixels")
    estimated_object_height_m: Optional[float] = Field(
        None, description="Estimated physical elevation off seabed in meters using hydrographic shadow formula"
    )


class ShadowAnalysisResult(BaseModel):
    detection_id: str = Field(..., description="Associated debris detection identifier")
    class_name: str = Field(..., description="Class of the debris object (e.g. shipwreck, aircraft)")
    has_shadow: bool = Field(..., description="True if a statistically valid acoustic shadow was extracted")
    shadow_score: float = Field(..., ge=0.0, le=1.0, description="Composite physical shadow confidence score [0.0 - 1.0]")
    confidence_adjustment: float = Field(
        0.0, description="Recommended adjustment to object detection confidence (-0.20 to +0.20)"
    )
    candidate: Optional[ShadowCandidate] = Field(None, description="Extracted shadow region")
    spatial_relationship: Optional[SpatialRelationship] = Field(None, description="Highlight-to-shadow relationship")
    direction: Optional[ShadowDirection] = Field(None, description="Shadow orientation and ray alignment")
    extent: Optional[ShadowExtent] = Field(None, description="Geometric extent and estimated target height")
    quality_assessment: str = Field(
        ..., description="Qualitative evaluation: Strong Shadow, Moderate Shadow, Weak Shadow, or None"
    )


class ShadowAnalysisResponse(BaseModel):
    status: str = Field("success", description="Analysis execution status")
    total_detections_analyzed: int = Field(..., description="Total detection items examined")
    shadows_confirmed: int = Field(..., description="Number of items with validated acoustic shadows")
    average_shadow_score: float = Field(..., description="Mean shadow score across all targets")
    results: List[ShadowAnalysisResult] = Field(default_factory=list, description="Per-detection shadow breakdown")
    annotated_overlay_base64: Optional[str] = Field(
        None, description="Base64 JPEG image showing detection boxes, shadow contours, and projection rays"
    )
