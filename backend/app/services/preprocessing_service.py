"""
Preprocessing Service for Sonar and Marine Debris Imagery.
Provides acoustic noise filtering, contrast equalization (CLAHE),
illumination/gamma correction, shadow boundary sharpening,
false-color sonar mapping, and geometric normalization.
"""

import io
import time
import base64
import logging
from typing import Optional, Tuple, Dict, Any, List

import cv2
import numpy as np
from PIL import Image

from app.schemas.preprocessing import (
    PreprocessingConfig,
    PreprocessingPreset,
    ColormapType,
    ImageStats,
    PreprocessingResponse,
    PresetInfo,
)

logger = logging.getLogger("marinescan.services.preprocessing")


class PreprocessingService:
    """Service to process raw and sonar imagery to optimize detection and visualization."""

    # Color map mapping to OpenCV colormaps
    COLORMAP_MAPPING = {
        ColormapType.AMBER: cv2.COLORMAP_HOT,       # Classic copper/amber acoustic intensity
        ColormapType.INFERNO: cv2.COLORMAP_INFERNO, # High dynamic range scientific
        ColormapType.VIRIDIS: cv2.COLORMAP_VIRIDIS, # Perceptually uniform
        ColormapType.OCEAN: cv2.COLORMAP_OCEAN,     # Bathymetric ocean depth
        ColormapType.BONE: cv2.COLORMAP_BONE,       # Cool grayscale with acoustic tint
        ColormapType.JET: cv2.COLORMAP_JET,         # Multi-spectral acoustic return
    }

    # Curated Preset Definitions
    PRESET_CONFIGS: Dict[PreprocessingPreset, PreprocessingConfig] = {
        PreprocessingPreset.BALANCED: PreprocessingConfig(
            preset=PreprocessingPreset.BALANCED,
            enable_denoise=True,
            denoise_method="bilateral",
            denoise_strength=7,
            enable_clahe=True,
            clahe_clip_limit=2.5,
            clahe_tile_grid_size=8,
            gamma=1.0,
            enable_sharpen=False,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
        PreprocessingPreset.SONAR_ACOUSTIC: PreprocessingConfig(
            preset=PreprocessingPreset.SONAR_ACOUSTIC,
            enable_denoise=True,
            denoise_method="bilateral",
            denoise_strength=9,
            enable_clahe=True,
            clahe_clip_limit=3.5,
            clahe_tile_grid_size=8,
            gamma=1.05,
            enable_sharpen=True,
            sharpen_amount=1.2,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
        PreprocessingPreset.TURBID_WATER: PreprocessingConfig(
            preset=PreprocessingPreset.TURBID_WATER,
            enable_denoise=True,
            denoise_method="median",
            denoise_strength=5,
            enable_clahe=True,
            clahe_clip_limit=4.0,
            clahe_tile_grid_size=8,
            gamma=0.85,  # Brightens dark underwater shadows
            enable_sharpen=True,
            sharpen_amount=0.8,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
        PreprocessingPreset.EDGE_ENHANCE: PreprocessingConfig(
            preset=PreprocessingPreset.EDGE_ENHANCE,
            enable_denoise=True,
            denoise_method="bilateral",
            denoise_strength=5,
            enable_clahe=True,
            clahe_clip_limit=2.5,
            clahe_tile_grid_size=8,
            gamma=1.0,
            enable_sharpen=True,
            sharpen_amount=1.8,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
        PreprocessingPreset.RAW_NORMALIZE: PreprocessingConfig(
            preset=PreprocessingPreset.RAW_NORMALIZE,
            enable_denoise=False,
            enable_clahe=False,
            gamma=1.0,
            enable_sharpen=False,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
        PreprocessingPreset.FAST: PreprocessingConfig(
            preset=PreprocessingPreset.FAST,
            enable_denoise=True,
            denoise_method="gaussian",
            denoise_strength=5,
            enable_clahe=True,
            clahe_clip_limit=2.0,
            clahe_tile_grid_size=8,
            gamma=1.0,
            enable_sharpen=False,
            colormap=ColormapType.NONE,
            preserve_aspect_ratio=True,
        ),
    }

    # Preset descriptive metadata
    PRESET_METADATA: Dict[PreprocessingPreset, Dict[str, str]] = {
        PreprocessingPreset.BALANCED: {
            "display_name": "Balanced Standard",
            "description": "Standard bilateral noise reduction and adaptive histogram equalization.",
            "recommended_for": "General purpose optical and sidescan sonar inspection.",
        },
        PreprocessingPreset.SONAR_ACOUSTIC: {
            "display_name": "Sonar Acoustic Enhancement",
            "description": "Aggressive speckle reduction, high CLAHE contrast, and shadow boundary sharpening.",
            "recommended_for": "High-frequency sidescan sonar (SSS) and forward-looking sonar (FLS).",
        },
        PreprocessingPreset.TURBID_WATER: {
            "display_name": "Turbid Water Dehaze",
            "description": "Adaptive contrast boost and illumination lift to penetrate murky or sediment-laden water.",
            "recommended_for": "Low-visibility river, harbor, or estuarine environments.",
        },
        PreprocessingPreset.EDGE_ENHANCE: {
            "display_name": "Edge & Structural Detail",
            "description": "Unsharp masking prioritized to expose aircraft frames, ship hulls, and geometric debris edges.",
            "recommended_for": "Man-made debris search and wreckage structural verification.",
        },
        PreprocessingPreset.RAW_NORMALIZE: {
            "display_name": "Raw Min-Max Normalization",
            "description": "Linear dynamic range normalization without non-linear filtering.",
            "recommended_for": "High-fidelity sonar analysis and quantitative sensor inspection.",
        },
        PreprocessingPreset.FAST: {
            "display_name": "Fast Real-Time",
            "description": "Low-latency Gaussian smoothing and light CLAHE suitable for high-FPS video streams.",
            "recommended_for": "Live ROV video feeds and real-time scanning.",
        },
    }

    # -------------------------------------------------------------------------
    # Core Filter Operators
    # -------------------------------------------------------------------------

    def denoise(self, image: np.ndarray, method: str = "bilateral", strength: int = 7) -> np.ndarray:
        """Apply edge-preserving or smoothing filter to suppress acoustic speckle noise."""
        k = strength if strength % 2 == 1 else strength + 1

        if method == "bilateral":
            # Bilateral filter preserves sharp boundaries while smoothing texture
            sigma = float(k * 7)
            return cv2.bilateralFilter(image, d=k, sigmaColor=sigma, sigmaSpace=sigma)
        elif method == "median":
            # Median filter eliminates impulsive salt-and-pepper backscatter
            return cv2.medianBlur(image, ksize=k)
        elif method == "gaussian":
            return cv2.GaussianBlur(image, (k, k), 0)
        return image

    def apply_clahe(self, image: np.ndarray, clip_limit: float = 2.5, tile_grid_size: int = 8) -> np.ndarray:
        """
        Contrast Limited Adaptive Histogram Equalization.
        If color image, transforms to LAB space and enhances L-channel only to avoid color distortion.
        """
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid_size, tile_grid_size))

        if len(image.shape) == 2 or image.shape[2] == 1:
            # Grayscale sonar
            gray = image if len(image.shape) == 2 else image[:, :, 0]
            return clahe.apply(gray)
        else:
            # 3-channel BGR
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            lab_planes = list(cv2.split(lab))
            lab_planes[0] = clahe.apply(lab_planes[0])
            lab = cv2.merge(lab_planes)
            return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def adjust_gamma(self, image: np.ndarray, gamma: float = 1.0) -> np.ndarray:
        """
        Apply power-law (gamma) illumination adjustment via fast lookup table.
        gamma < 1.0 brightens shadows/midtones (e.g. 0.8 in turbid water).
        gamma > 1.0 increases contrast/darkens midtones.
        """
        if abs(gamma - 1.0) < 0.01:
            return image

        exponent = max(0.05, float(gamma))
        table = np.array([((i / 255.0) ** exponent) * 255.0 for i in range(256)]).astype("uint8")
        return cv2.LUT(image, table)

    def sharpen(self, image: np.ndarray, amount: float = 1.0) -> np.ndarray:
        """Enhance acoustic shadow boundaries and debris edges using unsharp masking."""
        if amount <= 0.0:
            return image

        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=2.0)
        # unsharp mask: original * (1 + amount) - blurred * amount
        sharpened = cv2.addWeighted(image, 1.0 + amount, blurred, -amount, 0)
        return np.clip(sharpened, 0, 255).astype(np.uint8)

    def apply_colormap(self, image: np.ndarray, colormap: ColormapType) -> np.ndarray:
        """Map single-channel acoustic intensity to standard sonar visualization colormaps."""
        if colormap == ColormapType.NONE or colormap not in self.COLORMAP_MAPPING:
            return image

        cv_map = self.COLORMAP_MAPPING[colormap]

        # Convert to single channel grayscale if multi-channel
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        elif len(image.shape) == 3 and image.shape[2] == 1:
            gray = image[:, :, 0]
        else:
            gray = image

        return cv2.applyColorMap(gray, cv_map)

    def letterbox_resize(
        self,
        image: np.ndarray,
        target_width: int,
        target_height: int,
        fill_value: int = 0,
    ) -> np.ndarray:
        """
        Resize image preserving aspect ratio with zero/fill padding (letterboxing).
        Ideal for preparing inputs for YOLO object detection models.
        """
        orig_h, orig_w = image.shape[:2]
        scale = min(target_width / orig_w, target_height / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR)

        # Create canvas
        channels = 3 if len(image.shape) == 3 and image.shape[2] == 3 else 1
        if channels == 3:
            canvas = np.full((target_height, target_width, 3), fill_value, dtype=np.uint8)
        else:
            canvas = np.full((target_height, target_width), fill_value, dtype=np.uint8)

        # Center resized image in canvas
        pad_x = (target_width - new_w) // 2
        pad_y = (target_height - new_h) // 2
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized

        return canvas

    def compute_image_stats(self, image: np.ndarray) -> ImageStats:
        """Calculate statistical contrast, dynamic range, and estimated SNR."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 and image.shape[2] == 3 else image
        mean_val = float(np.mean(gray))
        std_val = float(np.std(gray))
        min_val = int(np.min(gray))
        max_val = int(np.max(gray))
        dynamic_range = max_val - min_val

        # Estimated SNR in dB: 20 * log10(mean / (std + eps))
        snr_db = 20.0 * np.log10(max(1e-4, mean_val) / max(1e-4, std_val))

        return ImageStats(
            mean_intensity=round(mean_val, 2),
            std_intensity=round(std_val, 2),
            min_intensity=min_val,
            max_intensity=max_val,
            dynamic_range=dynamic_range,
            estimated_snr_db=round(float(snr_db), 2),
        )

    # -------------------------------------------------------------------------
    # Pipeline Orchestration
    # -------------------------------------------------------------------------

    def resolve_config(self, config: Optional[PreprocessingConfig] = None) -> PreprocessingConfig:
        """Resolve config, applying preset defaults if preset is requested."""
        if config is None:
            return self.PRESET_CONFIGS[PreprocessingPreset.BALANCED].model_copy()

        if config.preset and config.preset in self.PRESET_CONFIGS:
            preset_base = self.PRESET_CONFIGS[config.preset].model_copy()
            # If user explicitly requested sizing overrides, carry them over
            if config.target_width is not None:
                preset_base.target_width = config.target_width
            if config.target_height is not None:
                preset_base.target_height = config.target_height
            if config.colormap != ColormapType.NONE:
                preset_base.colormap = config.colormap
            return preset_base

        return config

    def process_image(
        self,
        image_bgr: np.ndarray,
        config: Optional[PreprocessingConfig] = None,
        return_base64: bool = False,
    ) -> Tuple[np.ndarray, PreprocessingResponse]:
        """
        Execute full preprocessing pipeline on a BGR/Grayscale NumPy array.
        """
        start_time = time.perf_counter()
        cfg = self.resolve_config(config)

        input_h, input_w = image_bgr.shape[:2]
        input_stats = self.compute_image_stats(image_bgr)
        applied_steps: List[str] = []

        processed = image_bgr.copy()

        # Step 1: Denoise
        if cfg.enable_denoise:
            processed = self.denoise(processed, method=cfg.denoise_method, strength=cfg.denoise_strength)
            applied_steps.append(f"denoise_{cfg.denoise_method}(k={cfg.denoise_strength})")

        # Step 2: CLAHE Contrast Equalization
        if cfg.enable_clahe:
            processed = self.apply_clahe(
                processed, clip_limit=cfg.clahe_clip_limit, tile_grid_size=cfg.clahe_tile_grid_size
            )
            applied_steps.append(f"clahe(clip={cfg.clahe_clip_limit}, grid={cfg.clahe_tile_grid_size})")

        # Step 3: Gamma Illumination
        if abs(cfg.gamma - 1.0) > 0.01:
            processed = self.adjust_gamma(processed, gamma=cfg.gamma)
            applied_steps.append(f"gamma_correction({cfg.gamma})")

        # Step 4: Sharpening
        if cfg.enable_sharpen and cfg.sharpen_amount > 0.0:
            processed = self.sharpen(processed, amount=cfg.sharpen_amount)
            applied_steps.append(f"unsharp_mask(amount={cfg.sharpen_amount})")

        # Step 5: False-Color Sonar Colormap
        if cfg.colormap != ColormapType.NONE:
            processed = self.apply_colormap(processed, colormap=cfg.colormap)
            applied_steps.append(f"colormap({cfg.colormap.value})")

        # Step 6: Normalization & Letterbox Resizing
        if cfg.target_width is not None and cfg.target_height is not None:
            if cfg.preserve_aspect_ratio:
                processed = self.letterbox_resize(
                    processed, target_width=cfg.target_width, target_height=cfg.target_height
                )
                applied_steps.append(f"letterbox_resize({cfg.target_width}x{cfg.target_height})")
            else:
                processed = cv2.resize(
                    processed, (cfg.target_width, cfg.target_height), interpolation=cv2.INTER_LINEAR
                )
                applied_steps.append(f"direct_resize({cfg.target_width}x{cfg.target_height})")

        # Final check: Ensure 3-channel BGR for downstream model compatibility
        if len(processed.shape) == 2 or (len(processed.shape) == 3 and processed.shape[2] == 1):
            processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)

        output_h, output_w = processed.shape[:2]
        output_stats = self.compute_image_stats(processed)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        b64_str = None
        if return_base64:
            b64_str = self.encode_to_base64(processed)

        response = PreprocessingResponse(
            status="success",
            pipeline_duration_ms=round(duration_ms, 2),
            applied_steps=applied_steps,
            input_stats=input_stats,
            output_stats=output_stats,
            input_dimensions=(input_w, input_h),
            output_dimensions=(output_w, output_h),
            processed_image_base64=b64_str,
        )

        return processed, response

    def process_bytes(
        self,
        image_bytes: bytes,
        config: Optional[PreprocessingConfig] = None,
        return_base64: bool = False,
    ) -> Tuple[np.ndarray, PreprocessingResponse]:
        """Decode raw image bytes and execute the preprocessing pipeline."""
        if not image_bytes:
            raise ValueError("Empty image data received.")

        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_bgr is None or img_bgr.size == 0:
            raise ValueError("Failed to decode image data into OpenCV array.")

        return self.process_image(img_bgr, config=config, return_base64=return_base64)

    def encode_to_jpeg_bytes(self, image_bgr: np.ndarray, quality: int = 92) -> bytes:
        """Encode image to JPEG byte buffer."""
        success, encoded = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not success:
            raise ValueError("Failed to encode processed image to JPEG format.")
        return encoded.tobytes()

    def encode_to_base64(self, image_bgr: np.ndarray, quality: int = 92) -> str:
        """Encode image to base64 data URI."""
        jpeg_bytes = self.encode_to_jpeg_bytes(image_bgr, quality=quality)
        return f"data:image/jpeg;base64,{base64.b64encode(jpeg_bytes).decode('utf-8')}"

    def get_presets(self) -> List[PresetInfo]:
        """Return catalogue of all supported preprocessing presets with metadata."""
        presets_list = []
        for preset_enum, config in self.PRESET_CONFIGS.items():
            meta = self.PRESET_METADATA.get(preset_enum, {})
            presets_list.append(
                PresetInfo(
                    preset=preset_enum,
                    display_name=meta.get("display_name", preset_enum.value),
                    description=meta.get("description", ""),
                    recommended_for=meta.get("recommended_for", ""),
                    config=config,
                )
            )
        return presets_list


# Global service instance
preprocessing_service = PreprocessingService()
