"""
API Router for Master Pipeline Survey Analysis.
Provides high-level endpoints for running the unified 12-stage analysis pipeline
and generating annotated visual overlay images for UI components.
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response
import cv2

from app.services.master_pipeline_service import master_pipeline_service
from app.services.input_service import InputValidationError
from app.services.shadow_service import shadow_service
from app.ml.postprocess import render_detections_overlay, encode_image_to_jpeg_bytes
from app.services.image_output_service import image_output_service
from app.schemas.analysis import MasterAnalysisResult
from app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.analyses")

router = APIRouter()


@router.post(
    "/analyze",
    response_model=MasterAnalysisResult,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input or corrupted image"},
        500: {"model": ErrorResponse, "description": "Master pipeline execution failure"},
    },
    summary="Execute Master 12-Stage Intelligence Pipeline",
    description=(
        "Upload a sonar image to execute the complete master pipeline: "
        "Input validation → Quality check → Preprocessing → YOLO detection → "
        "Candidate extraction → Shadow evidence → Physics validation → Confidence fusion → "
        "Geolocation → Dimension estimation → Risk classification → Final intelligence report."
    ),
)
async def analyze_sonar_survey(
    file: UploadFile = File(..., description="Raw sonar or camera image file"),
    vessel_lat: float = Query(24.8607, description="Survey vessel / sensor latitude in WGS84 degrees"),
    vessel_lon: float = Query(67.0011, description="Survey vessel / sensor longitude in WGS84 degrees"),
    vessel_heading_deg: float = Query(0.0, ge=0.0, lt=360.0, description="Vessel gyro heading in degrees"),
    cable_payout_m: Optional[float] = Query(None, ge=0.0, description="Towfish cable payout in meters"),
    fish_depth_m: Optional[float] = Query(None, ge=0.0, description="Towfish depth below water surface in meters"),
    water_depth_m: float = Query(30.0, gt=0.0, description="Total water column depth at survey area (m)"),
    meters_per_pixel: float = Query(0.05, gt=0.0, description="Ground sampling distance in meters/pixel"),
    nadir_x: Optional[float] = Query(None, description="Center nadir ground-track pixel coordinate"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sensor altitude off seafloor in meters"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Estimated target slant range in meters"),
    confidence_threshold: float = Query(0.25, ge=0.01, le=1.0, description="Detection confidence threshold"),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic", description="Acoustic enhancement preset"),
    use_tiling: bool = Query(False, description="Enable high-resolution sliding-window tiling"),
    mission_id: Optional[str] = Query(None, description="Optional mission or survey identifier"),
) -> MasterAnalysisResult:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        result = master_pipeline_service.execute_pipeline(
            image_bytes=image_bytes,
            vessel_lat=vessel_lat,
            vessel_lon=vessel_lon,
            vessel_heading_deg=vessel_heading_deg,
            cable_payout_m=cable_payout_m,
            fish_depth_m=fish_depth_m,
            water_depth_m=water_depth_m,
            meters_per_pixel=meters_per_pixel,
            nadir_x=nadir_x,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            use_tiling=use_tiling,
            return_visualization=True,
            mission_id=mission_id,
        )
        return result

    except InputValidationError as ive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ive))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Master pipeline execution error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Master pipeline execution failed: {str(exc)}",
        )


@router.post(
    "/visualize",
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Rendered annotated sonar image"},
        400: {"model": ErrorResponse, "description": "Invalid input image"},
        500: {"model": ErrorResponse, "description": "Visualization failure"},
    },
    summary="Generate Master Visual Overlay Image",
    description="Upload a sonar image to receive directly a rendered JPEG overlay with bounding boxes, cyan shadow polygons, and yellow projection rays.",
)
async def visualize_sonar_survey(
    file: UploadFile = File(..., description="Raw sonar or camera image file"),
    vessel_lat: float = Query(24.8607),
    vessel_lon: float = Query(67.0011),
    vessel_heading_deg: float = Query(0.0),
    water_depth_m: float = Query(30.0),
    meters_per_pixel: float = Query(0.05),
    nadir_x: Optional[float] = Query(None),
    confidence_threshold: float = Query(0.25),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
) -> Response:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        analysis = master_pipeline_service.execute_pipeline(
            image_bytes=image_bytes,
            vessel_lat=vessel_lat,
            vessel_lon=vessel_lon,
            vessel_heading_deg=vessel_heading_deg,
            water_depth_m=water_depth_m,
            meters_per_pixel=meters_per_pixel,
            nadir_x=nadir_x,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            return_visualization=False,
        )

        # Decode original image
        from app.services.input_service import input_service
        img_bgr, _ = input_service.validate_and_decode(image_bytes)

        # Render shadow overlay
        det_dicts = [
            {
                "detection_id": t.detection_id,
                "class_id": t.class_id,
                "class_name": t.class_name,
                "display_name": t.display_name,
                "category": t.category,
                "confidence": t.ai_confidence,
                "bbox": t.bbox.model_dump(),
                "color_hex": t.color_hex,
            }
            for t in analysis.targets
        ]

        # Shadow results mapping
        from app.schemas.shadow import ShadowAnalysisResult, ShadowDirection, ShadowExtent
        shadow_results = []
        for t in analysis.targets:
            if t.shadow_evidence.has_shadow:
                shd_res = ShadowAnalysisResult(
                    detection_id=t.detection_id,
                    class_name=t.class_name,
                    has_shadow=True,
                    shadow_score=t.shadow_evidence.shadow_score,
                    direction=ShadowDirection(
                        angle_degrees=t.shadow_evidence.direction_degrees,
                        cardinal_direction=t.shadow_evidence.cardinal_direction,
                        nadir_relative_alignment=1.0,
                    ),
                    extent=ShadowExtent(
                        length_pixels=t.shadow_evidence.shadow_length_m / meters_per_pixel if t.shadow_evidence.shadow_length_m else 20.0,
                        width_pixels=t.bbox.width,
                        aspect_ratio=1.5,
                        area_pixels=100.0,
                        estimated_object_height_m=t.shadow_evidence.estimated_height_m,
                    ),
                    quality_assessment=(
                        "Strong Shadow"
                        if t.shadow_evidence.shadow_score >= 0.8
                        else "Moderate Shadow"
                        if t.shadow_evidence.shadow_score >= 0.5
                        else "Weak Shadow"
                    ),
                )
                shadow_results.append(shd_res)

        rendered_bgr = shadow_service.render_shadow_overlay(img_bgr, shadow_results)
        rendered_bgr = render_detections_overlay(rendered_bgr, det_dicts)
        jpeg_bytes = encode_image_to_jpeg_bytes(rendered_bgr)
        image_output_service.save_and_upload(jpeg_bytes, prefix="master_visualize")

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": "inline; filename=master_analysis_overlay.jpg",
                "X-Targets-Detected": str(len(analysis.targets)),
                "X-Max-Risk-Tier": analysis.summary.risk_tier_breakdown and max(analysis.summary.risk_tier_breakdown, key=analysis.summary.risk_tier_breakdown.get) or "NONE",
            },
        )

    except InputValidationError as ive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ive))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Visualization error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Visualization failed: {str(exc)}",
        )
