"""
API Router for Multi-Source Confidence Calibration & Explainability.
Fuses AI Model Confidence, Physics & Shadow Evidence, and Acoustic Image Quality
into calibrated trust tiers with human-readable engineering explanations.
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status
import cv2
import numpy as np

try:
    from app.services.confidence_service import confidence_service
    from app.services.inference_service import inference_service
    from app.services.shadow_service import shadow_service
    from app.services.physics_service import physics_service
    from app.schemas.confidence import (
        TargetConfidenceProfile,
        BatchConfidenceResponse,
    )
    from app.schemas.detection import BoundingBox
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.confidence_service import confidence_service
    from backend.app.services.inference_service import inference_service
    from backend.app.services.shadow_service import shadow_service
    from backend.app.services.physics_service import physics_service
    from backend.app.schemas.confidence import (
        TargetConfidenceProfile,
        BatchConfidenceResponse,
    )
    from backend.app.schemas.detection import BoundingBox
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.confidence")

router = APIRouter()


@router.post(
    "/evaluate-target",
    response_model=TargetConfidenceProfile,
    summary="Evaluate Single Target Confidence",
    description="Fuse AI detection confidence, physics validation score, and local image quality for a specific target.",
)
async def evaluate_target_confidence(
    class_name: str = Query(..., description="Target class (shipwreck, aircraft, fish, other)"),
    raw_ai_confidence: float = Query(..., ge=0.0, le=1.0, description="Raw model confidence"),
    length_m: float = Query(..., gt=0.0, description="Target length in meters"),
    width_m: float = Query(..., gt=0.0, description="Target width in meters"),
    shadow_score: Optional[float] = Query(None, ge=0.0, le=1.0, description="Optional acoustic shadow score"),
    quality_score: Optional[float] = Query(0.85, ge=0.0, le=1.0, description="Optional local image quality score"),
) -> TargetConfidenceProfile:
    try:
        # Generate representative local patch based on quality_score
        patch_size = 100
        base_val = 80
        img_patch = np.full((patch_size, patch_size), base_val, dtype=np.uint8)
        # Add target contrast scaled by quality_score
        contrast_add = int(quality_score * 120)
        cv2.rectangle(img_patch, (20, 20), (80, 80), base_val + contrast_add, -1)

        bbox = BoundingBox(
            x_min=20.0, y_min=20.0, x_max=80.0, y_max=80.0,
            width=60.0, height=60.0,
            normalized_x_min=0.2, normalized_y_min=0.2,
            normalized_x_max=0.8, normalized_y_max=0.8,
        )

        shadow_res = None
        if shadow_score is not None:
            from app.schemas.shadow import ShadowAnalysisResult
            shadow_res = ShadowAnalysisResult(
                detection_id="manual_target",
                class_name=class_name,
                has_shadow=(shadow_score > 0.1),
                shadow_score=shadow_score,
                confidence_adjustment=0.10 if shadow_score >= 0.6 else -0.05,
                quality_assessment="Corroborated Shadow" if shadow_score >= 0.6 else "Weak Shadow",
            )

        profile = confidence_service.evaluate_target_confidence(
            image_gray=img_patch,
            detection_id="manual_target",
            class_name=class_name,
            raw_ai_confidence=raw_ai_confidence,
            bbox=bbox,
            length_m=length_m,
            width_m=width_m,
            shadow_result=shadow_res,
        )
        return profile

    except Exception as exc:
        logger.exception("Target confidence evaluation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confidence evaluation failed: {str(exc)}",
        )


@router.post(
    "/analyze-image",
    response_model=BatchConfidenceResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Confidence analysis failure"},
    },
    summary="End-to-End Confidence Calibration from Sonar Image",
    description="Upload a sonar image to execute AI detection, acoustic shadow extraction, physics analysis, and multi-source confidence fusion.",
)
async def analyze_image_confidence(
    file: UploadFile = File(..., description="Sonar image file"),
    meters_per_pixel: float = Query(0.05, gt=0.0, description="Ground sampling distance (m/px)"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sonar altitude off seabed (m)"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Target slant range (m)"),
    nadir_x: Optional[float] = Query(None, description="Nadir ground-track coordinate"),
    confidence_threshold: Optional[float] = Query(0.25),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
) -> BatchConfidenceResponse:
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

        # 2. Shadow Evidence
        shadow_resp = shadow_service.analyze_all_detections(
            image_bgr=img_bgr,
            detections=det_dicts,
            nadir_x=nadir_x,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            return_overlay=False,
        )

        # 3. Physics Evaluation
        physics_resp = physics_service.enrich_detections_with_physics(
            detections=det_dicts,
            shadow_results=shadow_resp.results,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )

        # 4. Multi-Source Confidence Fusion
        conf_response = confidence_service.evaluate_all_detections(
            image_gray=img_gray,
            detections=det_dicts,
            shadow_results=shadow_resp.results,
            physics_analyses=physics_resp.results,
            meters_per_pixel=meters_per_pixel,
        )

        return conf_response

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Confidence analysis error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Confidence analysis failed: {str(exc)}",
        )
