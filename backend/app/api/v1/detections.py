"""
Detection API endpoints for MarineScan.
Provides endpoints for running YOLO object detection on marine imagery
(single image, batched, high-resolution tiled, and binary visualization).
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response

try:
    from app.services.inference_service import inference_service
    from app.schemas.detection import DetectionResponse, BatchDetectionResponse, TilingConfig
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.inference_service import inference_service
    from backend.app.schemas.detection import DetectionResponse, BatchDetectionResponse, TilingConfig
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.detections")

router = APIRouter()

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "application/octet-stream",
}


@router.post(
    "/predict",
    response_model=DetectionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file or parameters"},
        500: {"model": ErrorResponse, "description": "Inference failure"},
    },
    summary="Detect Marine Debris",
    description="Upload an image file to detect marine debris (aircraft, fish, other, shipwreck) with optional sliding-window tiling and real-world dimension estimation.",
)
async def predict_detections(
    file: UploadFile = File(..., description="Image file (JPEG, PNG, WebP, BMP, TIFF)"),
    confidence_threshold: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence cutoff threshold (0.0 - 1.0). Overrides default setting.",
    ),
    iou_threshold: Optional[float] = Query(
        0.45,
        ge=0.0,
        le=1.0,
        description="IoU threshold for Non-Maximum Suppression (NMS).",
    ),
    return_visualization: bool = Query(
        True,
        description="Whether to include Base64-encoded annotated image in response.",
    ),
    classes: Optional[List[str]] = Query(
        None,
        description="Filter specific debris classes to return (e.g. ['shipwreck', 'aircraft']).",
    ),
    preprocessing_preset: Optional[str] = Query(
        None,
        description="Optional preprocessing preset ('balanced', 'sonar_acoustic', 'turbid_water', 'edge_enhance').",
    ),
    meters_per_pixel: Optional[float] = Query(
        None,
        gt=0.0,
        description="Ground sampling distance / resolution in meters per pixel to estimate real-world dimensions.",
    ),
    use_tiling: bool = Query(
        False,
        description="Enable sliding-window tiling for wide or tall high-resolution sonar scans.",
    ),
) -> DetectionResponse:
    if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
        logger.warning("Unrecognized MIME type: %s, attempting decode anyway.", file.content_type)

    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            return_visualization=return_visualization,
            classes_filter=classes,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
            use_tiling=use_tiling,
        )
        return response

    except HTTPException:
        raise
    except ValueError as ve:
        logger.error("Image decode error: %s", ve)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        logger.exception("Inference error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference execution failed: {str(exc)}",
        )


@router.post(
    "/predict-batch",
    response_model=BatchDetectionResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input files"},
        500: {"model": ErrorResponse, "description": "Batch processing failure"},
    },
    summary="Batch Detect Marine Debris",
    description="Upload multiple images simultaneously for parallel batched YOLO inference.",
)
async def predict_detections_batch(
    files: List[UploadFile] = File(..., description="Multiple image files to process"),
    confidence_threshold: Optional[float] = Query(None, ge=0.0, le=1.0),
    iou_threshold: Optional[float] = Query(0.45, ge=0.0, le=1.0),
    return_visualization: bool = Query(False, description="Include Base64 image per item"),
    preprocessing_preset: Optional[str] = Query(None),
    meters_per_pixel: Optional[float] = Query(None, gt=0.0),
) -> BatchDetectionResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided in request.")

    try:
        bytes_list: List[bytes] = []
        for f in files:
            content = await f.read()
            if content:
                bytes_list.append(content)

        if not bytes_list:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All uploaded files are empty.")

        response = inference_service.predict_batch(
            image_bytes_list=bytes_list,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            return_visualization=return_visualization,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
        )
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Batch inference error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch inference failed: {str(exc)}",
        )


@router.post(
    "/visualize",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "Rendered JPEG image with drawn bounding boxes and labels.",
        },
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Visualization failure"},
    },
    summary="Visualize Detections",
    description="Upload an image file and receive the annotated image directly as JPEG binary with drawn bounding boxes.",
)
async def visualize_detections(
    file: UploadFile = File(..., description="Image file to analyze"),
    confidence_threshold: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence cutoff threshold (0.0 - 1.0).",
    ),
    iou_threshold: Optional[float] = Query(
        0.45,
        ge=0.0,
        le=1.0,
        description="IoU threshold for NMS.",
    ),
    preprocessing_preset: Optional[str] = Query(
        None,
        description="Optional preprocessing preset ('balanced', 'sonar_acoustic', 'turbid_water', 'edge_enhance').",
    ),
    use_tiling: bool = Query(
        False,
        description="Enable sliding-window tiling for high-resolution images.",
    ),
    meters_per_pixel: Optional[float] = Query(
        None,
        gt=0.0,
        description="GSD in meters per pixel.",
    ),
):
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        jpeg_bytes, det_count = inference_service.predict_and_render_image(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            preprocessing_preset=preprocessing_preset,
            use_tiling=use_tiling,
            meters_per_pixel=meters_per_pixel,
        )

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "X-Detections-Count": str(det_count),
                "Content-Disposition": f'inline; filename="detected_{file.filename or "image.jpg"}"',
            },
        )

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        logger.exception("Visualization error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image visualization failed: {str(exc)}",
        )
