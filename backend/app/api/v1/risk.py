"""
API Router for Maritime Risk, Navigational Clearance, and Safety Directives.
Provides endpoints for evaluating under-keel clearance, trawl entanglement risk,
subsea infrastructure threats, environmental hazards, and generating IHO/NOTMAR directives.
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status
import cv2

try:
    from app.services.risk_service import risk_service
    from app.services.inference_service import inference_service
    from app.services.shadow_service import shadow_service
    from app.services.physics_service import physics_service
    from app.services.confidence_service import confidence_service
    from app.schemas.risk import (
        TargetRiskAssessment,
        BatchRiskResponse,
    )
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.risk_service import risk_service
    from backend.app.services.inference_service import inference_service
    from backend.app.services.shadow_service import shadow_service
    from backend.app.services.physics_service import physics_service
    from backend.app.services.confidence_service import confidence_service
    from backend.app.schemas.risk import (
        TargetRiskAssessment,
        BatchRiskResponse,
    )
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.risk")

router = APIRouter()


@router.post(
    "/evaluate-target",
    response_model=TargetRiskAssessment,
    summary="Evaluate Single Target Maritime Risk",
    description="Compute under-keel clearance, trawl snag risk, infrastructure threat, environmental rating, and action recommendations for a specific debris target.",
)
async def evaluate_target_risk(
    class_name: str = Query(..., description="Target class (shipwreck, aircraft, fish, other)"),
    length_m: float = Query(..., gt=0.0, description="Target length in meters"),
    width_m: float = Query(..., gt=0.0, description="Target width in meters"),
    height_m: float = Query(..., gt=0.0, description="Target height off seabed in meters"),
    water_depth_m: float = Query(30.0, gt=0.0, description="Water column depth in meters"),
    distance_to_cable_m: Optional[float] = Query(None, gt=0.0, description="Optional distance to pipeline/cable in meters"),
) -> TargetRiskAssessment:
    try:
        assessment = risk_service.assess_target_risk(
            detection_id="manual_target",
            class_name=class_name,
            length_m=length_m,
            width_m=width_m,
            height_m=height_m,
            water_depth_m=water_depth_m,
            distance_to_cable_m=distance_to_cable_m,
        )
        return assessment

    except Exception as exc:
        logger.exception("Target risk evaluation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Target risk evaluation failed: {str(exc)}",
        )


@router.post(
    "/analyze-image",
    response_model=BatchRiskResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Risk assessment failure"},
    },
    summary="End-to-End Maritime Risk Assessment from Sonar Image",
    description="Upload a sonar image to execute AI detection, shadow height estimation, physics analysis, confidence calibration, and comprehensive maritime risk assessment.",
)
async def analyze_image_risk(
    file: UploadFile = File(..., description="Sonar image file"),
    water_depth_m: float = Query(30.0, gt=0.0, description="Survey area water depth in meters"),
    meters_per_pixel: float = Query(0.05, gt=0.0, description="Ground sampling distance in meters/pixel"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sonar altitude off seabed (m)"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Target slant range (m)"),
    nadir_x: Optional[float] = Query(None, description="Nadir ground-track coordinate"),
    confidence_threshold: Optional[float] = Query(0.25),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
) -> BatchRiskResponse:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        # 1. AI Detection
        det_response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
            return_visualization=False,
        )

        img_bgr, _ = inference_service.decode_image_bytes(image_bytes)
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        det_dicts = [d.model_dump() for d in det_response.detections]

        # 2. Shadow Analysis (extracts vertical relief)
        shadow_resp = shadow_service.analyze_all_detections(
            image_bgr=img_bgr,
            detections=det_dicts,
            nadir_x=nadir_x,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            return_overlay=False,
        )

        # 3. Physics Analysis (hydrodynamic stability, submerged mass)
        physics_resp = physics_service.enrich_detections_with_physics(
            detections=det_dicts,
            shadow_results=shadow_resp.results,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )

        # 4. Confidence Calibration (trust tiers)
        conf_response = confidence_service.evaluate_all_detections(
            image_gray=img_gray,
            detections=det_dicts,
            shadow_results=shadow_resp.results,
            physics_analyses=physics_resp.results,
            meters_per_pixel=meters_per_pixel,
        )

        # 5. Maritime Risk Assessment
        risk_resp = risk_service.assess_batch_risk(
            detections=det_dicts,
            water_depth_m=water_depth_m,
            physics_analyses=physics_resp.results,
            confidence_profiles=conf_response.results,
            meters_per_pixel=meters_per_pixel,
        )

        return risk_resp

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Risk analysis error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Maritime risk analysis failed: {str(exc)}",
        )
