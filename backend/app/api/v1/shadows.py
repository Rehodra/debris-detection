"""
API Router for Sonar Acoustic Shadow Analytics.
Provides endpoints for extracting and scoring acoustic shadows cast by detected debris,
verifying 3D protrusion off the seabed, and rendering shadow projection overlays.
"""

import logging
from typing import Optional, Tuple
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response

try:
    from app.services.shadow_service import shadow_service
    from app.services.inference_service import inference_service
    from app.schemas.shadow import ShadowAnalysisResponse
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.shadow_service import shadow_service
    from backend.app.services.inference_service import inference_service
    from backend.app.schemas.shadow import ShadowAnalysisResponse
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.shadows")

router = APIRouter()


@router.post(
    "/analyze",
    response_model=ShadowAnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Shadow analysis failure"},
    },
    summary="Analyze Acoustic Shadows",
    description="Detect debris and extract acoustic shadows behind targets to evaluate 3D physical confidence, orientation, and seabed height.",
)
async def analyze_shadows(
    file: UploadFile = File(..., description="Sonar image file"),
    nadir_x: Optional[float] = Query(
        None, description="Nadir ground-track line horizontal pixel coordinate (for SSS left/right ray alignment)"
    ),
    sensor_x: Optional[float] = Query(None, description="Acoustic transducer X coordinate (for FLS)"),
    sensor_y: Optional[float] = Query(None, description="Acoustic transducer Y coordinate (for FLS)"),
    meters_per_pixel: Optional[float] = Query(None, gt=0.0, description="Ground sampling distance in meters per pixel"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Altitude of sonar fish/vessel off seabed in meters"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Slant range distance to target in meters"),
    confidence_threshold: Optional[float] = Query(0.25, ge=0.0, le=1.0, description="Detection confidence cutoff"),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic", description="Sonar enhancement preset"),
    return_overlay: bool = Query(True, description="Include Base64 rendered overlay in response"),
) -> ShadowAnalysisResponse:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        # 1. Run detection (with preprocessing enhancement)
        det_response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            return_visualization=False,
        )

        # 2. Decode raw image for shadow extraction
        img_bgr, _ = inference_service.decode_image_bytes(image_bytes)

        # 3. Format detections into dictionaries
        det_dicts = [d.model_dump() for d in det_response.detections]
        sensor_pos = (sensor_x, sensor_y) if sensor_x is not None and sensor_y is not None else None

        # 4. Execute 6-stage shadow analysis pipeline
        shadow_resp = shadow_service.analyze_all_detections(
            image_bgr=img_bgr,
            detections=det_dicts,
            nadir_x=nadir_x,
            sensor_pos=sensor_pos,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            return_overlay=return_overlay,
        )

        return shadow_resp

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Shadow analysis error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Acoustic shadow analysis failed: {str(exc)}",
        )


@router.post(
    "/visualize",
    responses={
        200: {
            "content": {"image/jpeg": {}},
            "description": "Rendered JPEG with highlighted debris, cyan shadow polygons, and acoustic rays.",
        },
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Visualization failure"},
    },
    summary="Visualize Acoustic Shadows",
    description="Upload a sonar image and receive the annotated image with highlighted targets, cyan shadow footprints, and projection arrows.",
)
async def visualize_shadows(
    file: UploadFile = File(..., description="Sonar image file"),
    nadir_x: Optional[float] = Query(None, description="Nadir ground-track coordinate"),
    meters_per_pixel: Optional[float] = Query(None, gt=0.0, description="Meters per pixel resolution"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sensor altitude off seabed (meters)"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Target slant range (meters)"),
    confidence_threshold: Optional[float] = Query(0.25, ge=0.0, le=1.0),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
):
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        det_response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            return_visualization=False,
        )

        img_bgr, _ = inference_service.decode_image_bytes(image_bytes)
        det_dicts = [d.model_dump() for d in det_response.detections]

        shadow_resp = shadow_service.analyze_all_detections(
            image_bgr=img_bgr,
            detections=det_dicts,
            nadir_x=nadir_x,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            return_overlay=False,
        )

        rendered_bgr = shadow_service.render_shadow_overlay(img_bgr, shadow_resp.results)
        from app.ml.postprocess import encode_image_to_jpeg_bytes
        jpeg_bytes = encode_image_to_jpeg_bytes(rendered_bgr)

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "X-Shadows-Confirmed": str(shadow_resp.shadows_confirmed),
                "Content-Disposition": f'inline; filename="shadow_{file.filename or "sonar.jpg"}"',
            },
        )

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Shadow visualization error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Shadow visualization failed: {str(exc)}",
        )
