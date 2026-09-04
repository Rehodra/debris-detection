"""
Pydantic schemas for object detection requests, responses, bounding boxes,
model metadata, and physical dimension estimations.
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x_min: float = Field(..., description="Top-left X coordinate in pixels")
    y_min: float = Field(..., description="Top-left Y coordinate in pixels")
    x_max: float = Field(..., description="Bottom-right X coordinate in pixels")
    y_max: float = Field(..., description="Bottom-right Y coordinate in pixels")
    width: float = Field(..., description="Box width in pixels")
    height: float = Field(..., description="Box height in pixels")
    normalized_x_min: float = Field(..., description="Normalized top-left X [0.0 - 1.0]")
    normalized_y_min: float = Field(..., description="Normalized top-left Y [0.0 - 1.0]")
    normalized_x_max: float = Field(..., description="Normalized bottom-right X [0.0 - 1.0]")
    normalized_y_max: float = Field(..., description="Normalized bottom-right Y [0.0 - 1.0]")


class PhysicalDimensions(BaseModel):
    length_meters: float = Field(..., description="Estimated physical length along longest axis in meters")
    width_meters: float = Field(..., description="Estimated physical width along shortest axis in meters")
    area_sq_meters: float = Field(..., description="Estimated seabed footprint area in square meters")
    meters_per_pixel: float = Field(..., description="Ground sampling distance / resolution used for calculation")


class DetectionItem(BaseModel):
    detection_id: str = Field(..., description="Unique detection identifier")
    class_id: int = Field(..., description="Integer class index")
    class_name: str = Field(..., description="Canonical class name")
    display_name: str = Field(..., description="Human-friendly label")
    category: str = Field(..., description="Debris category")
    risk_level: str = Field(..., description="Hazard/risk classification: Critical, High, Moderate, Low")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score [0.0 - 1.0]")
    bbox: BoundingBox = Field(..., description="Bounding box coordinates")
    area_pixels: float = Field(..., description="Area of detection box in square pixels")
    color_hex: str = Field(..., description="Hex color for bounding box UI rendering")
    color_rgb: List[int] = Field(..., description="RGB color tuple [R, G, B]")
    physical_dimensions: Optional[PhysicalDimensions] = Field(
        None, description="Real-world estimated dimensions when image resolution/GSD is provided"
    )


class DetectionSummary(BaseModel):
    total_detections: int = Field(..., description="Total count of detected objects above threshold")
    class_counts: Dict[str, int] = Field(default_factory=dict, description="Count of detections per class")
    max_confidence: float = Field(0.0, description="Highest confidence among all detections")
    critical_detected: bool = Field(False, description="True if any high/critical risk debris detected")


class ImageMetadata(BaseModel):
    width: int = Field(..., description="Image width in pixels")
    height: int = Field(..., description="Image height in pixels")
    channels: int = Field(3, description="Color channels count")
    format: Optional[str] = Field(None, description="Original image format (JPEG, PNG, etc.)")


class TimingBreakdown(BaseModel):
    decode_time_ms: float = Field(0.0, description="Image decode duration in milliseconds")
    preprocessing_time_ms: float = Field(0.0, description="Sonar filter / enhancement duration in milliseconds")
    inference_time_ms: float = Field(0.0, description="YOLO model forward pass duration in milliseconds")
    postprocess_time_ms: float = Field(0.0, description="NMS and coordinate parsing duration in milliseconds")
    total_time_ms: float = Field(0.0, description="End-to-end processing pipeline duration in milliseconds")


class TilingConfig(BaseModel):
    tile_size: int = Field(640, ge=256, le=2048, description="Square tile dimension in pixels")
    overlap_ratio: float = Field(0.20, ge=0.05, le=0.50, description="Tile overlap ratio (0.05 to 0.50)")
    iou_merge_threshold: float = Field(0.40, ge=0.1, le=0.9, description="Global NMS IoU threshold for merging tiles")


class DetectionResponse(BaseModel):
    status: str = Field("success", description="Detection execution status")
    model_name: str = Field("MarineScan YOLOv8 Debris Detector", description="Model identifier")
    device: str = Field(..., description="Inference compute device (cpu, cuda, mps)")
    inference_time_ms: float = Field(..., description="Model inference duration in milliseconds")
    total_time_ms: float = Field(..., description="Total pipeline duration")
    timing_breakdown: Optional[TimingBreakdown] = Field(None, description="Detailed stage latency telemetry")
    image_info: ImageMetadata = Field(..., description="Image dimensions and format")
    detections: List[DetectionItem] = Field(default_factory=list, description="List of detected debris objects")
    summary: DetectionSummary = Field(..., description="Aggregated detection statistics")
    tiling_applied: bool = Field(False, description="Whether high-res sliding-window tiling was utilized")
    annotated_image_base64: Optional[str] = Field(
        None, description="Optional Base64-encoded JPEG image with rendered bounding boxes"
    )


class BatchDetectionResponse(BaseModel):
    status: str = Field("success", description="Batch processing execution status")
    total_images: int = Field(..., description="Number of images processed")
    total_detections: int = Field(..., description="Total detections found across all images")
    batch_duration_ms: float = Field(..., description="Total batch runtime in milliseconds")
    results: List[DetectionResponse] = Field(default_factory=list, description="List of per-image detection responses")


class ModelInfoResponse(BaseModel):
    is_loaded: bool = Field(..., description="Whether model weights are loaded in memory")
    device: str = Field(..., description="Compute device utilized (cpu, cuda, mps)")
    weights_path: str = Field(..., description="Resolved path to model weights file")
    weights_size_mb: float = Field(..., description="Size of weights file in megabytes")
    classes: Dict[int, str] = Field(..., description="Mapping of class IDs to class names")
    total_classes: int = Field(..., description="Total number of supported classes")
    task: str = Field(..., description="Vision task (detect, segment, classify)")
    load_duration_ms: float = Field(..., description="Time taken to load model into memory")
    default_confidence_threshold: float = Field(..., description="Default inference confidence cutoff")


class ClassInfoResponse(BaseModel):
    class_id: int
    name: str
    display_name: str
    category: str
    risk_level: str
    color_hex: str
    color_rgb: List[int]
    description: str
