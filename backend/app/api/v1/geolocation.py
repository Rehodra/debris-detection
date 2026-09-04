"""
API Router for Marine Debris Geolocation, Geodesy, and Navigation Mapping.
Provides endpoints for calculating towfish catenary layback, translating sonar pixels
into WGS84/UTM coordinates, and outputting standard RFC 7946 GeoJSON FeatureCollections.
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response

try:
    from app.services.geolocation_service import geolocation_service
    from app.services.inference_service import inference_service
    from app.schemas.geolocation import (
        NavigationalFix,
        TowfishConfig,
        SonarScanOrigin,
        GeoCoordinates,
        GeolocatedTarget,
        BatchGeolocationResponse,
    )
    from app.schemas.common import ErrorResponse
except ImportError:
    from backend.app.services.geolocation_service import geolocation_service
    from backend.app.services.inference_service import inference_service
    from backend.app.schemas.geolocation import (
        NavigationalFix,
        TowfishConfig,
        SonarScanOrigin,
        GeoCoordinates,
        GeolocatedTarget,
        BatchGeolocationResponse,
    )
    from backend.app.schemas.common import ErrorResponse

logger = logging.getLogger("marinescan.api.geolocation")

router = APIRouter()


@router.post(
    "/layback",
    response_model=GeoCoordinates,
    summary="Compute Towfish Layback Coordinates",
    description="Calculate the true geographic position of a towed sonar body behind the surface vessel using cable length and depth.",
)
async def compute_towfish_layback(
    vessel_lat: float = Query(..., ge=-90.0, le=90.0, description="Surface vessel GPS latitude"),
    vessel_lon: float = Query(..., ge=-180.0, le=180.0, description="Surface vessel GPS longitude"),
    vessel_heading_deg: float = Query(..., ge=0.0, le=360.0, description="Vessel gyro heading in degrees true"),
    cable_payout_m: float = Query(..., gt=0.0, description="Tow cable length deployed (m)"),
    fish_depth_m: float = Query(..., ge=0.0, description="Towfish depth below surface (m)"),
    catenary_factor: float = Query(0.95, ge=0.7, le=1.0, description="Catenary correction factor (default: 0.95)"),
) -> GeoCoordinates:
    try:
        vessel_fix = NavigationalFix(
            latitude=vessel_lat,
            longitude=vessel_lon,
            heading_degrees=vessel_heading_deg,
        )
        towfish_cfg = TowfishConfig(
            cable_payout_m=cable_payout_m,
            fish_depth_m=fish_depth_m,
            catenary_factor=catenary_factor,
        )

        fish_coords, _ = geolocation_service.calculate_towfish_position(vessel_fix, towfish_cfg)
        return fish_coords

    except Exception as exc:
        logger.exception("Layback calculation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Towfish layback calculation failed: {str(exc)}",
        )


@router.post(
    "/target",
    response_model=GeolocatedTarget,
    summary="Geolocate Single Sonar Target",
    description="Compute geographic coordinates (WGS84, DMS, UTM) for a target detected at given pixel coordinates.",
)
async def geolocate_target_endpoint(
    pixel_x: float = Query(..., description="Target centroid pixel X"),
    pixel_y: float = Query(..., description="Target centroid pixel Y"),
    class_name: str = Query("shipwreck", description="Debris class"),
    confidence: float = Query(0.85, ge=0.0, le=1.0),
    sensor_lat: float = Query(..., ge=-90.0, le=90.0, description="Sensor latitude"),
    sensor_lon: float = Query(..., ge=-180.0, le=180.0, description="Sensor longitude"),
    sensor_heading_deg: float = Query(..., ge=0.0, le=360.0, description="Sensor heading in degrees true"),
    nadir_pixel_x: float = Query(500.0, description="Nadir center-track column index"),
    across_track_gsd_m: float = Query(0.05, gt=0.0, description="Across-track resolution (m/px)"),
    along_track_gsd_m: float = Query(0.05, gt=0.0, description="Along-track resolution (m/px)"),
    target_depth_m: Optional[float] = Query(None, description="Seafloor depth (m)"),
) -> GeolocatedTarget:
    try:
        nav_fix = NavigationalFix(
            latitude=sensor_lat,
            longitude=sensor_lon,
            heading_degrees=sensor_heading_deg,
        )
        origin = SonarScanOrigin(
            nadir_pixel_x=nadir_pixel_x,
            across_track_gsd_m=across_track_gsd_m,
            along_track_gsd_m=along_track_gsd_m,
        )

        target = geolocation_service.geolocate_target(
            target_id="manual_target",
            class_name=class_name,
            confidence=confidence,
            pixel_x=pixel_x,
            pixel_y=pixel_y,
            nav_fix=nav_fix,
            sonar_origin=origin,
            target_depth_m=target_depth_m,
        )
        return target

    except Exception as exc:
        logger.exception("Target geolocation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Target geolocation failed: {str(exc)}",
        )


@router.post(
    "/analyze-image",
    response_model=BatchGeolocationResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid image file"},
        500: {"model": ErrorResponse, "description": "Geolocation failure"},
    },
    summary="End-to-End Sonar Image Detection and Geolocation",
    description="Upload a sonar image with navigation metadata to run YOLO detection, geolocate all debris targets, and generate GeoJSON features.",
)
async def analyze_image_geolocation(
    file: UploadFile = File(..., description="Sonar image file"),
    vessel_lat: float = Query(..., ge=-90.0, le=90.0, description="GPS Latitude"),
    vessel_lon: float = Query(..., ge=-180.0, le=180.0, description="GPS Longitude"),
    vessel_heading_deg: float = Query(..., ge=0.0, le=360.0, description="True gyro heading (deg)"),
    nadir_pixel_x: Optional[float] = Query(None, description="Nadir ground-track column (defaults to image center)"),
    meters_per_pixel: float = Query(0.05, gt=0.0, description="Ground sampling distance in meters/pixel"),
    cable_payout_m: Optional[float] = Query(None, gt=0.0, description="Towfish cable payout (m) if towed"),
    fish_depth_m: Optional[float] = Query(None, ge=0.0, description="Towfish depth (m) if towed"),
    confidence_threshold: Optional[float] = Query(0.25),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic"),
) -> BatchGeolocationResponse:
    try:
        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        # 1. Run AI Detection
        det_response = inference_service.predict(
            image_bytes=image_bytes,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            meters_per_pixel=meters_per_pixel,
            return_visualization=False,
        )

        det_dicts = [d.model_dump() for d in det_response.detections]
        img_w = det_response.image_info.width

        # Default nadir to center column if not supplied
        nadir_x = nadir_pixel_x if nadir_pixel_x is not None else (img_w / 2.0)

        nav_fix = NavigationalFix(
            latitude=vessel_lat,
            longitude=vessel_lon,
            heading_degrees=vessel_heading_deg,
        )
        origin = SonarScanOrigin(
            nadir_pixel_x=nadir_x,
            across_track_gsd_m=meters_per_pixel,
            along_track_gsd_m=meters_per_pixel,
        )

        towfish_cfg = None
        if cable_payout_m is not None and fish_depth_m is not None:
            towfish_cfg = TowfishConfig(
                cable_payout_m=cable_payout_m,
                fish_depth_m=fish_depth_m,
            )

        # 2. Geolocate All Detections & Construct GeoJSON
        geo_response = geolocation_service.geolocate_batch(
            detections=det_dicts,
            nav_fix=nav_fix,
            sonar_origin=origin,
            towfish_cfg=towfish_cfg,
        )

        return geo_response

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as exc:
        logger.exception("Image geolocation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image geolocation analysis failed: {str(exc)}",
        )
