"""
API Router for Sonar and Marine Debris Preprocessing.
Provides endpoints for enhancing raw acoustic and underwater imagery,
inspecting image statistics, testing presets, and direct binary preview.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response

try:
    from app.services.preprocessing_service import preprocessing_service
    from app.schemas.preprocessing import (
        PreprocessingConfig,
        PreprocessingPreset,
        ColormapType,
        PreprocessingResponse,
        PresetInfo,
    )
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.preprocessing_service import preprocessing_service
    from backend.app.schemas.preprocessing import (
        PreprocessingConfig,
        PreprocessingPreset,
        ColormapType,
        PreprocessingResponse,
        PresetInfo,
    )
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.preprocessing")

router = APIRouter()


@router.get(
    "/presets",
    response_model=List[PresetInfo],
    summary="List Preprocessing Presets",
    description="Retrieve available sonar and underwater optical enhancement presets and their default configurations.",
)
async def list_presets() -> List[PresetInfo]:
    return preprocessing_service.get_presets()


@router.post(
    "/process",
    response_model=PreprocessingResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file or parameters"},
        500: {"model": ErrorResponse, "description": "Preprocessing failure"},
    },
    summary="Preprocess Marine / Sonar Image",
    description="Enhance an image using curated acoustic presets (e.g. sonar_acoustic, turbid_water) or custom filter parameters.",
)
async def preprocess_image(
    file: UploadFile = File(..., description="Image file to process"),
    preset: Optional[PreprocessingPreset] = Query(
        None,
        description="Filter preset ('balanced', 'sonar_acoustic', 'turbid_water', 'edge_enhance', 'fast')",
    ),
    enable_denoise: Optional[bool] = Query(None, description="Toggle edge-preserving denoising"),
    denoise_method: Optional[str] = Query(None, description="'bilateral', 'median', or 'gaussian'"),
    denoise_strength: Optional[int] = Query(None, ge=3, le=25, description="Filter kernel size (odd int)"),
    enable_clahe: Optional[bool] = Query(None, description="Toggle CLAHE contrast equalization"),
    clahe_clip_limit: Optional[float] = Query(None, ge=0.5, le=10.0, description="CLAHE contrast clip limit"),
    gamma: Optional[float] = Query(None, ge=0.2, le=3.0, description="Gamma correction exponent"),
    enable_sharpen: Optional[bool] = Query(None, description="Toggle acoustic shadow sharpening"),
    sharpen_amount: Optional[float] = Query(None, ge=0.1, le=3.0, description="Sharpening factor"),
    colormap: Optional[ColormapType] = Query(None, description="Apply false-color sonar palette"),
    target_width: Optional[int] = Query(None, ge=64, le=4096, description="Resize target width"),
    target_height: Optional[int] = Query(None, ge=64, le=4096, description="Resize target height"),
    return_base64: bool = Query(True, description="Include Base64 encoded JPEG in response"),
) -> PreprocessingResponse:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        # Build config based on preset or custom overrides
        if preset:
            base_config = preprocessing_service.PRESET_CONFIGS.get(
                preset, preprocessing_service.PRESET_CONFIGS[PreprocessingPreset.BALANCED]
            ).model_copy()
        else:
            base_config = PreprocessingConfig()

        if enable_denoise is not None:
            base_config.enable_denoise = enable_denoise
        if denoise_method is not None:
            base_config.denoise_method = denoise_method
        if denoise_strength is not None:
            base_config.denoise_strength = denoise_strength
        if enable_clahe is not None:
            base_config.enable_clahe = enable_clahe
        if clahe_clip_limit is not None:
            base_config.clahe_clip_limit = clahe_clip_limit
        if gamma is not None:
            base_config.gamma = gamma
        if enable_sharpen is not None:
            base_config.enable_sharpen = enable_sharpen
        if sharpen_amount is not None:
            base_config.sharpen_amount = sharpen_amount
        if colormap is not None:
            base_config.colormap = colormap
        if target_width is not None:
            base_config.target_width = target_width
        if target_height is not None:
            base_config.target_height = target_height

        _, response = preprocessing_service.process_bytes(
            image_bytes=image_bytes,
            config=base_config,
            return_base64=return_base64,
        )
        return response

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error("Preprocessing value error: %s", ve)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Preprocessing failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image preprocessing failed: {str(exc)}",
        )


@router.post(
    "/preview",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "Direct enhanced JPEG binary image.",
        },
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Processing failure"},
    },
    summary="Preview Preprocessed Image",
    description="Upload an image and receive the enhanced image directly as a JPEG binary stream.",
)
async def preview_preprocessed_image(
    file: UploadFile = File(..., description="Image to enhance"),
    preset: Optional[PreprocessingPreset] = Query(
        PreprocessingPreset.BALANCED,
        description="Enhancement preset",
    ),
    colormap: Optional[ColormapType] = Query(
        ColormapType.NONE,
        description="Sonar false-color palette",
    ),
    gamma: Optional[float] = Query(1.0, ge=0.2, le=3.0, description="Gamma correction factor"),
):
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        cfg = preprocessing_service.PRESET_CONFIGS.get(
            preset or PreprocessingPreset.BALANCED,
            preprocessing_service.PRESET_CONFIGS[PreprocessingPreset.BALANCED],
        ).model_copy()

        if colormap and colormap != ColormapType.NONE:
            cfg.colormap = colormap
        if gamma is not None:
            cfg.gamma = gamma

        processed_bgr, _ = preprocessing_service.process_bytes(
            image_bytes=image_bytes,
            config=cfg,
            return_base64=False,
        )
        jpeg_bytes = preprocessing_service.encode_to_jpeg_bytes(processed_bgr)

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="enhanced_{file.filename or "image.jpg"}"',
            },
        )

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Preview failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image enhancement preview failed: {str(exc)}",
        )
