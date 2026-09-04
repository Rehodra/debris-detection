"""
Pydantic schemas for Sonar and Marine Debris Image Preprocessing.
Defines configurations, filter options, telemetry stats, and responses.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel, Field


class PreprocessingPreset(str, Enum):
    BALANCED = "balanced"
    SONAR_ACOUSTIC = "sonar_acoustic"
    TURBID_WATER = "turbid_water"
    EDGE_ENHANCE = "edge_enhance"
    RAW_NORMALIZE = "raw_normalize"
    FAST = "fast"


class ColormapType(str, Enum):
    NONE = "none"
    AMBER = "amber"          # Classic sidescan sonar copper/amber
    INFERNO = "inferno"      # High contrast perceptual
    VIRIDIS = "viridis"      # Perceptually uniform
    OCEAN = "ocean"          # Hydrographic bathymetric blue
    BONE = "bone"            # Grayscale with light blue tint
    JET = "jet"              # Rainbow acoustic intensity


class PreprocessingConfig(BaseModel):
    preset: Optional[PreprocessingPreset] = Field(
        None, description="Pre-configured filter pipeline (overrides individual options if set)"
    )
    # Denoising
    enable_denoise: bool = Field(True, description="Enable edge-preserving noise reduction")
    denoise_method: str = Field("bilateral", description="Denoise algorithm: 'bilateral', 'median', or 'gaussian'")
    denoise_strength: int = Field(9, ge=3, le=25, description="Filter kernel size or strength (odd int)")
    
    # Contrast & CLAHE
    enable_clahe: bool = Field(True, description="Enable Contrast-Limited Adaptive Histogram Equalization")
    clahe_clip_limit: float = Field(2.5, ge=0.5, le=10.0, description="CLAHE contrast cutoff threshold")
    clahe_tile_grid_size: int = Field(8, ge=2, le=32, description="Tile grid size (e.g. 8 for 8x8 blocks)")
    
    # Illumination / Gamma
    gamma: float = Field(1.0, ge=0.2, le=3.0, description="Gamma correction exponent (1.0 = neutral, <1 brighter, >1 darker)")
    
    # Edge & Acoustic Shadow Sharpening
    enable_sharpen: bool = Field(False, description="Sharpen acoustic shadow boundaries with unsharp masking")
    sharpen_amount: float = Field(1.0, ge=0.1, le=3.0, description="Sharpening strength factor")
    
    # False-Color Sonar Mapping
    colormap: ColormapType = Field(ColormapType.NONE, description="Apply false-color sonar palette to 1-channel images")
    
    # Sizing & Geometry
    target_width: Optional[int] = Field(None, ge=64, le=4096, description="Target output width")
    target_height: Optional[int] = Field(None, ge=64, le=4096, description="Target output height")
    preserve_aspect_ratio: bool = Field(True, description="Use letterboxing padding to preserve aspect ratio")


class ImageStats(BaseModel):
    mean_intensity: float = Field(..., description="Average pixel intensity [0 - 255]")
    std_intensity: float = Field(..., description="Pixel standard deviation (contrast indicator)")
    min_intensity: int = Field(..., description="Minimum pixel value")
    max_intensity: int = Field(..., description="Maximum pixel value")
    dynamic_range: int = Field(..., description="max - min pixel value")
    estimated_snr_db: float = Field(..., description="Estimated Signal-to-Noise Ratio in decibels")


class PreprocessingResponse(BaseModel):
    status: str = Field("success", description="Processing status")
    pipeline_duration_ms: float = Field(..., description="Total execution time in milliseconds")
    applied_steps: List[str] = Field(default_factory=list, description="List of filter operations performed")
    input_stats: ImageStats = Field(..., description="Image metrics before preprocessing")
    output_stats: ImageStats = Field(..., description="Image metrics after preprocessing")
    input_dimensions: Tuple[int, int] = Field(..., description="Original (width, height)")
    output_dimensions: Tuple[int, int] = Field(..., description="Result (width, height)")
    processed_image_base64: Optional[str] = Field(
        None, description="Base64 encoded JPEG/PNG preview string"
    )


class PresetInfo(BaseModel):
    preset: PreprocessingPreset
    display_name: str
    description: str
    recommended_for: str
    config: PreprocessingConfig
