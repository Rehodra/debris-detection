"""
API Router for Ocean Physics, Hydrography, and Debris Dynamics.
Provides endpoints for calculating seawater acoustics, slant-range ground corrections,
3D volumetric estimation, salvage crane lift ratings, and hydrodynamic seabed stability.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status

try:
    from app.services.physics_service import physics_service
    from app.services.inference_service import inference_service
    from app.services.shadow_service import shadow_service
    from app.schemas.physics import (
        SedimentType,
        OceanEnvironmentParams,
        AcousticEnvironment,
        TargetPhysicsAnalysis,
        BatchPhysicsResponse,
    )
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.physics_service import physics_service
    from backend.app.services.inference_service import inference_service
    from backend.app.services.shadow_service import shadow_service
    from backend.app.schemas.physics import (
        SedimentType,
        OceanEnvironmentParams,
        AcousticEnvironment,
        TargetPhysicsAnalysis,
        BatchPhysicsResponse,
    )
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.physics")

router = APIRouter()


@router.get(
    "/environment",
    response_model=AcousticEnvironment,
    summary="Compute Ocean Acoustic Environment",
    description="Calculate seawater speed of sound (Mackenzie 1981), acoustic absorption, and wavelength.",
)
async def get_acoustic_environment(
    temperature_c: float = Query(12.0, description="Water temperature in deg C"),
    salinity_ppt: float = Query(35.0, ge=0.0, le=45.0, description="Salinity in ppt/PSU"),
    depth_m: float = Query(30.0, ge=0.0, description="Water depth in meters"),
    sonar_frequency_khz: float = Query(450.0, gt=0.0, description="Sonar frequency in kHz"),
) -> AcousticEnvironment:
    try:
        env = physics_service.get_acoustic_environment(
            OceanEnvironmentParams(
                temperature_c=temperature_c,
                salinity_ppt=salinity_ppt,
                depth_m=depth_m,
                sonar_frequency_khz=sonar_frequency_khz,
            )
        )
        return env
    except Exception as exc:
        logger.exception("Environment calculation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Acoustic environment calculation failed: {str(exc)}",
        )


@router.post(
    "/analyze-target",
    response_model=TargetPhysicsAnalysis,
    summary="Analyze Single Target Physics",
    description="Compute 3D volume, mass, buoyancy, salvage crane lift rating, and hydrodynamic stability for a specific debris item.",
)
async def analyze_target_physics(
    class_name: str = Query(..., description="Class name: 'shipwreck', 'aircraft', 'fish', 'other'"),
    length_m: float = Query(..., gt=0.0, description="Length in meters"),
    width_m: float = Query(..., gt=0.0, description="Width in meters"),
    height_m: Optional[float] = Query(None, gt=0.0, description="Optional measured height in meters"),
    temperature_c: float = Query(12.0),
    salinity_ppt: float = Query(35.0),
    depth_m: float = Query(30.0),
    bottom_current_mps: float = Query(0.75),
    sediment_type: SedimentType = Query(SedimentType.FINE_SAND),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0),
    slant_range_m: Optional[float] = Query(None, gt=0.0),
) -> TargetPhysicsAnalysis:
    try:
        env = OceanEnvironmentParams(
            temperature_c=temperature_c,
            salinity_ppt=salinity_ppt,
            depth_m=depth_m,
            bottom_current_mps=bottom_current_mps,
            sediment_type=sediment_type,
        )

        analysis = physics_service.analyze_target_physics(
            detection_id="manual_target",
            class_name=class_name,
            confidence=1.0,
            length_m=length_m,
            width_m=width_m,
            env_params=env,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )
        return analysis

    except Exception as exc:
        logger.exception("Target physics error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Target physics analysis failed: {str(exc)}",
        )


@router.post(
    "/analyze-image",
    response_model=BatchPhysicsResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Physics synthesis failure"},
    },
    summary="End-to-End Physics Analysis from Sonar Image",
    description="Upload a sonar image to synthesize AI Detections + Shadow Evidence + Sonar Geometry into full physical & salvage analytics.",
)
async def analyze_image_physics(
    file: UploadFile = File(..., description="Sonar image file"),
    meters_per_pixel: float = Query(0.05, gt=0.0, description="Ground sampling distance (m/px)"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sonar altitude off seabed (m)"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Target slant range (m)"),
    nadir_x: Optional[float] = Query(None, description="Nadir ground-track coordinate"),
    temperature_c: float = Query(12.0),
    salinity_ppt: float = Query(35.0),
    depth_m: float = Query(30.0),
    bottom_current_mps: float = Query(0.75),
    sediment_type: SedimentType = Query(SedimentType.FINE_SAND),
    confidence_threshold: Optional[float] = Query(0.25),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
) -> BatchPhysicsResponse:
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

        # 2. Shadow Evidence
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

        # 3. Physics Synthesis
        env = OceanEnvironmentParams(
            temperature_c=temperature_c,
            salinity_ppt=salinity_ppt,
            depth_m=depth_m,
            bottom_current_mps=bottom_current_mps,
            sediment_type=sediment_type,
        )

        physics_resp = physics_service.enrich_detections_with_physics(
            detections=det_dicts,
            shadow_results=shadow_resp.results,
            env_params=env,
            meters_per_pixel=meters_per_pixel,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
        )

        return physics_resp

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Image physics analysis error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image physics analysis failed: {str(exc)}",
        )
