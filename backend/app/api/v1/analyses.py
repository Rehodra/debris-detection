"""
API Router for Master Pipeline Survey Analysis.
Provides high-level endpoints for running the unified 12-stage analysis pipeline
and generating annotated visual overlay images for UI components.
"""

import json
import logging
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Query, HTTPException, status, Response, Depends, Path as PathParam
from sqlalchemy.orm import Session
from sqlalchemy import desc
import cv2

from app.services.master_pipeline_service import master_pipeline_service
from app.services.input_service import InputValidationError
from app.services.sonar_ingestion_service import SonarIngestionError
from app.services.sonar_artifact_service import sonar_artifact_service
from app.services.hydrographic_export_service import hydrographic_export_service
from app.services.shadow_service import shadow_service
from app.ml.postprocess import render_detections_overlay, encode_image_to_jpeg_bytes
from app.services.image_output_service import image_output_service
from app.schemas.analysis import MasterAnalysisResult, SonarAnalysisResponse
from app.schemas.sonar import SonarNavigationTrack
from app.schemas.common import ErrorResponse
from app.db.session import get_db
from app.db.models import AnalysisRecord

logger = logging.getLogger("marinescan.api.analyses")

router = APIRouter()


def _persist_analysis(
    db: Session,
    result: MasterAnalysisResult,
    filename: str,
    vessel_lat: float,
    vessel_lon: float,
    vessel_heading_deg: float,
) -> None:
    """Best-effort persistence — a DB hiccup must never break the analysis response."""
    try:
        record = AnalysisRecord(
            mission_id=result.mission_id,
            filename=filename,
            vessel_lat=vessel_lat,
            vessel_lon=vessel_lon,
            vessel_heading_deg=vessel_heading_deg,
            total_targets=result.summary.total_targets_detected,
            verified_targets=result.summary.verified_targets,
            max_risk_tier=(
                max(
                    (t for t, c in result.summary.risk_tier_breakdown.items() if c > 0),
                    key=lambda t: result.summary.risk_tier_breakdown[t],
                    default=None,
                )
                if result.summary.total_targets_detected > 0
                else None
            ),
            class_breakdown=result.summary.class_breakdown,
            result_json=result.model_dump(mode="json"),
        )
        db.add(record)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to persist analysis record %s: %s", result.mission_id, exc)
        db.rollback()


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
    db: Session = Depends(get_db),
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
            filename=file.filename,
        )
        _persist_analysis(
            db, result, file.filename or "unknown", vessel_lat, vessel_lon, vessel_heading_deg
        )
        return result

    except (InputValidationError, SonarIngestionError) as ive:
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
    "/sonar",
    response_model=SonarAnalysisResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid or corrupt raw sonar recording"},
        422: {"model": ErrorResponse, "description": "Invalid analysis parameters"},
        500: {"model": ErrorResponse, "description": "Pipeline execution failure"},
    },
    summary="Execute Master Pipeline on Raw Sonar (.xtf / .jsf)",
    description=(
        "Upload an EdgeTech (.jsf) or Extended Triton (.xtf) raw sonar recording to execute "
        "the unified 12-stage MarineScan analysis pipeline directly on the decoded acoustic waterfall. "
        "Returns the unified SonarAnalysisResponse contract."
    ),
)
async def analyze_raw_sonar_file(
    file: UploadFile = File(..., description="Raw sonar recording file (.xtf or .jsf)"),
    max_pings: Optional[int] = Query(None, ge=1, description="Maximum number of along-track pings to process"),
    channels: Optional[List[str]] = Query(None, description="Optional channels to render (e.g. '0', '1', or '0,1')"),
    vessel_lat: float = Query(24.8607, description="Survey vessel / sensor latitude in WGS84 degrees"),
    vessel_lon: float = Query(67.0011, description="Survey vessel / sensor longitude in WGS84 degrees"),
    vessel_heading_deg: float = Query(0.0, ge=0.0, lt=360.0, description="Vessel gyro heading in degrees"),
    cable_payout_m: Optional[float] = Query(None, ge=0.0, description="Towfish cable payout in meters"),
    fish_depth_m: Optional[float] = Query(None, ge=0.0, description="Towfish depth below water surface in meters"),
    water_depth_m: float = Query(30.0, gt=0.0, description="Total water column depth at survey area (m)"),
    meters_per_pixel: Optional[float] = Query(None, gt=0.0, description="Manual override for meters/pixel (defaults to sonar telemetry if unprovided)"),
    nadir_x: Optional[float] = Query(None, description="Center nadir ground-track pixel coordinate"),
    sensor_altitude_m: Optional[float] = Query(None, gt=0.0, description="Sensor altitude off seafloor in meters"),
    slant_range_m: Optional[float] = Query(None, gt=0.0, description="Estimated target slant range in meters"),
    confidence_threshold: float = Query(0.25, ge=0.01, le=1.0, description="Detection confidence threshold"),
    preprocessing_preset: Optional[str] = Query("sonar_acoustic", description="Acoustic enhancement preset"),
    use_tiling: bool = Query(False, description="Enable high-resolution sliding-window tiling"),
    return_visualization: bool = Query(False, description="Whether to include base64-encoded annotated raster (defaults to False for lightweight JSON)"),
    mission_id: Optional[str] = Query(None, description="Optional mission or survey identifier"),
    db: Session = Depends(get_db),
) -> SonarAnalysisResponse:
    parsed_channels: Optional[List[int]] = None
    if channels:
        parsed_channels = []
        for item in channels:
            for part in str(item).split(","):
                c_str = part.strip()
                if c_str:
                    try:
                        val = int(c_str)
                        if val < 0:
                            raise HTTPException(status_code=422, detail=f"Channel ID must be non-negative, got {val}")
                        parsed_channels.append(val)
                    except ValueError:
                        raise HTTPException(status_code=422, detail=f"Invalid channel ID '{c_str}': must be integer")

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
            meters_per_pixel=meters_per_pixel or 0.05,
            nadir_x=nadir_x,
            sensor_altitude_m=sensor_altitude_m,
            slant_range_m=slant_range_m,
            confidence_threshold=confidence_threshold,
            preprocessing_preset=preprocessing_preset,
            use_tiling=use_tiling,
            return_visualization=return_visualization,
            mission_id=mission_id,
            filename=file.filename,
            max_pings=max_pings,
            channels=parsed_channels,
        )
        _persist_analysis(
            db, result, file.filename or "unknown", vessel_lat, vessel_lon, vessel_heading_deg
        )
        return SonarAnalysisResponse.from_analysis_result(
            result, filename=file.filename, file_size_bytes=len(image_bytes)
        )

    except (InputValidationError, SonarIngestionError) as ive:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ive))
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Master pipeline execution error on sonar recording: %s", exc)
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
                "X-Max-Risk-Tier": (
                    max(
                        (t for t, c in analysis.summary.risk_tier_breakdown.items() if c > 0),
                        key=lambda t: analysis.summary.risk_tier_breakdown[t],
                        default="NONE",
                    )
                    if analysis.summary.total_targets_detected > 0
                    else "NONE"
                ),
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


# -----------------------------------------------------------------------------
# History — real persisted analysis records (backs Dashboard aggregates and
# the History page). Every field here was actually computed by a real
# /analyses/analyze run; nothing here is synthesized.
# -----------------------------------------------------------------------------

@router.get(
    "/history",
    summary="List recent persisted analyses",
    description="Returns summary fields for the most recent analysis records, newest first.",
)
async def list_analysis_history(
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> List[dict]:
    records = (
        db.query(AnalysisRecord)
        .order_by(desc(AnalysisRecord.created_at))
        .limit(limit)
        .all()
    )
    return [
        {
            "mission_id": r.mission_id,
            "created_at": r.created_at.isoformat() if isinstance(r.created_at, datetime) else r.created_at,
            "filename": r.filename,
            "vessel_lat": r.vessel_lat,
            "vessel_lon": r.vessel_lon,
            "vessel_heading_deg": r.vessel_heading_deg,
            "total_targets": r.total_targets,
            "verified_targets": r.verified_targets,
            "max_risk_tier": r.max_risk_tier,
            "class_breakdown": r.class_breakdown,
        }
        for r in records
    ]


@router.get(
    "/history/{mission_id}",
    summary="Get the full stored result for one past analysis",
    responses={404: {"model": ErrorResponse, "description": "No record with that mission_id"}},
)
async def get_analysis_history_detail(
    mission_id: str,
    db: Session = Depends(get_db),
) -> dict:
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == mission_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No analysis found for mission_id={mission_id}")
    return record.result_json


@router.get(
    "/{analysis_id}/sonar/raster",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Normalized acoustic waterfall raster artifact (PNG) associated with the analysis ID.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found, non-sonar analysis, or physical artifact missing.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error retrieving raster artifact.",
        },
    },
    summary="Retrieve Analysis Sonar Waterfall Raster Artifact",
    description=(
        "Retrieve the exact, immutable acoustic waterfall raster artifact generated during "
        "a completed raw sonar analysis (.xtf / .jsf) by its unique analysis ID (mission ID). "
        "Returns the lossless PNG raster stream with acquisition geometry headers."
    ),
    tags=["Master Survey Analysis Pipeline", "Raw Sonar Ingestion"],
)
async def get_analysis_sonar_raster(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Locates the completed sonar analysis artifact, verifies its provenance, and returns
    the exact acoustic waterfall raster artifact as an image/png response.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()

    # 1. Invalid analysis ID
    if record is None:
        if not sonar_artifact_service.has_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )
        sonar_meta = sonar_artifact_service.get_artifact_metadata(analysis_id) or {}
    else:
        # 2. Check if analysis is a sonar analysis
        result_json = record.result_json or {}
        sonar_meta = result_json.get("sonar_metadata")
        if not sonar_meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' exists but was not generated from a raw sonar recording and contains no sonar raster artifact.",
            )

    # 3. Retrieve physical artifact bytes
    png_bytes = sonar_artifact_service.get_artifact_bytes(analysis_id)
    if not png_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sonar raster artifact for analysis '{analysis_id}' exists in metadata but physical artifact is missing from storage.",
        )

    # 4. Construct telemetry and acquisition headers
    width = sonar_meta.get("waterfall_width")
    height = sonar_meta.get("waterfall_height")
    channel_layout = sonar_meta.get("channel_layout", "unknown")
    total_pings = sonar_meta.get("total_pings", height)
    sonar_format = sonar_meta.get("format") or sonar_meta.get("sonar_format", "UNKNOWN")
    nadir_pixel_x = sonar_meta.get("nadir_pixel_x")
    meters_per_pixel = sonar_meta.get("meters_per_pixel")
    slant_range_m = sonar_meta.get("slant_range_m")
    artifact_id = sonar_meta.get("artifact_id") or f"art_{analysis_id}"

    headers = {
        "Content-Type": "image/png",
        "X-Analysis-ID": str(analysis_id),
        "X-Artifact-ID": str(artifact_id),
        "X-Raster-Width": str(width) if width is not None else "",
        "X-Raster-Height": str(height) if height is not None else "",
        "X-Channel-Layout": str(channel_layout),
        "X-Total-Pings": str(total_pings) if total_pings is not None else "",
        "X-Sonar-Format": str(sonar_format),
    }

    if nadir_pixel_x is not None:
        headers["X-Nadir-Pixel-X"] = f"{float(nadir_pixel_x):.1f}"
    else:
        headers["X-Nadir-Pixel-X"] = "null"

    if meters_per_pixel is not None:
        headers["X-Meters-Per-Pixel"] = f"{float(meters_per_pixel):.6f}"
    else:
        headers["X-Meters-Per-Pixel"] = "null"

    if slant_range_m is not None:
        headers["X-Slant-Range-M"] = f"{float(slant_range_m):.2f}"
    else:
        headers["X-Slant-Range-M"] = "null"

    json_meta = {
        "analysis_id": analysis_id,
        "artifact_id": artifact_id,
        "width": width,
        "height": height,
        "channel_layout": channel_layout,
        "nadir_pixel_x": nadir_pixel_x,
        "meters_per_pixel": meters_per_pixel,
        "slant_range_m": slant_range_m,
        "total_pings": total_pings,
        "channels_included": sonar_meta.get("channels_included", []),
        "format": sonar_format,
        "filename": sonar_meta.get("filename"),
    }
    headers["X-Sonar-Metadata"] = json.dumps(json_meta)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers=headers,
    )


@router.get(
    "/{analysis_id}/sonar/track",
    response_model=SonarNavigationTrack,
    responses={
        200: {
            "description": "Ordered sonar navigation track containing ping-by-ping telemetry.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found, non-sonar analysis, or physical track artifact missing.",
        },
    },
    summary="Retrieve Analysis Sonar Navigation Track",
    description=(
        "Retrieve the ordered ping-by-ping navigation track and telemetry associated with a "
        "completed raw sonar analysis (.xtf / .jsf) by its unique analysis ID."
    ),
    tags=["Master Survey Analysis Pipeline", "Raw Sonar Ingestion"],
)
async def get_analysis_sonar_track(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> SonarNavigationTrack:
    """
    Locates the completed sonar analysis artifact, verifies its provenance, and returns
    the ordered ping navigation track as structured JSON.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()

    if record is None:
        if not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)
    else:
        result_json = record.result_json or {}
        sonar_meta = result_json.get("sonar_metadata")
        if not sonar_meta or not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' exists but was not generated from a raw sonar recording and contains no sonar navigation track.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)

    if not track_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sonar navigation track artifact for analysis '{analysis_id}' is missing from storage.",
        )

    return SonarNavigationTrack.model_validate(track_dict)


# -----------------------------------------------------------------------------
# Phase 7 & 8: Hydrographic & Navigation Data Export
# -----------------------------------------------------------------------------

@router.get(
    "/{analysis_id}/export/json",
    response_class=Response,
    responses={
        200: {
            "content": {"application/json": {}},
            "description": "Complete structured MarineScan hydrographic and navigation JSON export.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found or stored result unavailable.",
        },
    },
    summary="Export Completed Analysis as Hydrographic JSON",
    description=(
        "Exports a completed sonar or camera survey analysis as a structured machine-readable "
        "hydrographic dataset including analysis metadata, navigation telemetry, acoustic artifact "
        "references, and detailed detection records with WGS84 coordinates and risk metrics."
    ),
    tags=["Master Survey Analysis Pipeline", "Hydrographic Export"],
)
async def export_analysis_json(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Retrieves stored analysis results and exports a full structured hydrographic JSON package.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )
    if not record.result_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' has no stored result.",
        )

    record_meta = {
        "mission_id": record.mission_id,
        "filename": record.filename,
        "created_at": record.created_at,
        "vessel_lat": record.vessel_lat,
        "vessel_lon": record.vessel_lon,
        "vessel_heading_deg": record.vessel_heading_deg,
    }
    payload = hydrographic_export_service.export_json(
        record.result_json, record_meta=record_meta, analysis_id=analysis_id
    )
    content = json.dumps(payload, indent=2)

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="marinescan_{analysis_id}.json"',
        },
    )


@router.get(
    "/{analysis_id}/export/csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Tabular CSV detection export with one row per detected target.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found or stored result unavailable.",
        },
    },
    summary="Export Completed Analysis Detections as CSV",
    description=(
        "Exports completed analysis detections as a tabular CSV dataset. Includes pixel bounding boxes, "
        "normalized coordinates, WGS84 positions, physical dimensions, and maritime risk scores."
    ),
    tags=["Master Survey Analysis Pipeline", "Hydrographic Export"],
)
async def export_analysis_csv(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Retrieves stored analysis results and exports a tabular detection CSV dataset.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )
    if not record.result_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' has no stored result.",
        )

    record_meta = {
        "mission_id": record.mission_id,
        "filename": record.filename,
        "created_at": record.created_at,
        "vessel_lat": record.vessel_lat,
        "vessel_lon": record.vessel_lon,
        "vessel_heading_deg": record.vessel_heading_deg,
    }
    content = hydrographic_export_service.export_csv(
        record.result_json, record_meta=record_meta, analysis_id=analysis_id
    )

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="marinescan_{analysis_id}.csv"',
        },
    )


@router.get(
    "/{analysis_id}/export/geojson",
    response_class=Response,
    responses={
        200: {
            "content": {"application/geo+json": {}},
            "description": "RFC 7946 GeoJSON FeatureCollection of geolocated targets with [longitude, latitude] coordinates.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found or stored result unavailable.",
        },
    },
    summary="Export Completed Analysis Detections as GeoJSON",
    description=(
        "Exports geolocated targets as an RFC 7946 GeoJSON FeatureCollection. "
        "Coordinates strictly adhere to the [longitude, latitude] standard."
    ),
    tags=["Master Survey Analysis Pipeline", "Hydrographic Export"],
)
async def export_analysis_geojson(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Retrieves stored analysis results and exports an RFC 7946 GeoJSON FeatureCollection.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' not found.",
        )
    if not record.result_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis '{analysis_id}' has no stored result.",
        )

    record_meta = {
        "mission_id": record.mission_id,
        "filename": record.filename,
        "created_at": record.created_at,
        "vessel_lat": record.vessel_lat,
        "vessel_lon": record.vessel_lon,
        "vessel_heading_deg": record.vessel_heading_deg,
    }
    payload = hydrographic_export_service.export_geojson(
        record.result_json, record_meta=record_meta, analysis_id=analysis_id
    )
    content = json.dumps(payload, indent=2)

    return Response(
        content=content,
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="marinescan_{analysis_id}.geojson"',
        },
    )


@router.get(
    "/{analysis_id}/export/track.geojson",
    response_class=Response,
    responses={
        200: {
            "content": {"application/geo+json": {}},
            "description": "RFC 7946 GeoJSON FeatureCollection containing the sonar acquisition track as a LineString.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found, non-sonar analysis, or track artifact missing.",
        },
    },
    summary="Export Analysis Sonar Acquisition Track as GeoJSON",
    description=(
        "Exports the vessel/vehicle navigation track as an RFC 7946 GeoJSON FeatureCollection. "
        "Coordinates strictly adhere to the [longitude, latitude] standard."
    ),
    tags=["Master Survey Analysis Pipeline", "Hydrographic Export"],
)
async def export_analysis_track_geojson(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Retrieves stored analysis track and exports an RFC 7946 GeoJSON FeatureCollection.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()
    if record is None:
        if not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)
        record_meta = {"mission_id": analysis_id}
    else:
        result_json = record.result_json or {}
        sonar_meta = result_json.get("sonar_metadata")
        if not sonar_meta or not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' exists but was not generated from a raw sonar recording and contains no sonar navigation track.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)
        record_meta = {
            "mission_id": record.mission_id,
            "filename": record.filename,
            "created_at": record.created_at,
            "vessel_lat": record.vessel_lat,
            "vessel_lon": record.vessel_lon,
            "vessel_heading_deg": record.vessel_heading_deg,
        }

    if not track_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sonar navigation track artifact for analysis '{analysis_id}' is missing from storage.",
        )

    payload = hydrographic_export_service.export_track_geojson(
        track_dict, record_meta=record_meta, analysis_id=analysis_id
    )
    content = json.dumps(payload, indent=2)

    return Response(
        content=content,
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="marinescan_{analysis_id}_track.geojson"',
        },
    )


@router.get(
    "/{analysis_id}/export/track.csv",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "Tabular CSV ping-by-ping navigation track export.",
        },
        404: {
            "model": ErrorResponse,
            "description": "Analysis ID not found, non-sonar analysis, or track artifact missing.",
        },
    },
    summary="Export Analysis Sonar Acquisition Track as CSV",
    description=(
        "Exports the ping-by-ping telemetry and navigation track as a tabular CSV dataset in acquisition order."
    ),
    tags=["Master Survey Analysis Pipeline", "Hydrographic Export"],
)
async def export_analysis_track_csv(
    analysis_id: str = PathParam(..., description="Unique analysis / mission identifier (e.g. 'msn_a1b2c3d4e5')"),
    db: Session = Depends(get_db),
) -> Response:
    """
    Retrieves stored analysis track and exports a tabular CSV dataset in acquisition order.
    """
    record = db.query(AnalysisRecord).filter(AnalysisRecord.mission_id == analysis_id).first()
    if record is None:
        if not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' not found.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)
        record_meta = {"mission_id": analysis_id}
    else:
        result_json = record.result_json or {}
        sonar_meta = result_json.get("sonar_metadata")
        if not sonar_meta or not sonar_artifact_service.has_track_artifact(analysis_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis '{analysis_id}' exists but was not generated from a raw sonar recording and contains no sonar navigation track.",
            )
        track_dict = sonar_artifact_service.get_track_artifact(analysis_id)
        record_meta = {
            "mission_id": record.mission_id,
            "filename": record.filename,
            "created_at": record.created_at,
            "vessel_lat": record.vessel_lat,
            "vessel_lon": record.vessel_lon,
            "vessel_heading_deg": record.vessel_heading_deg,
        }

    if not track_dict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sonar navigation track artifact for analysis '{analysis_id}' is missing from storage.",
        )

    content = hydrographic_export_service.export_track_csv(
        track_dict, record_meta=record_meta, analysis_id=analysis_id
    )

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="marinescan_{analysis_id}_track.csv"',
        },
    )


