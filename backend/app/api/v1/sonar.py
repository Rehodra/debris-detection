"""
Sonar API endpoints for MarineScan.
Provides endpoints for inspecting raw sonar recordings (.xtf, .jsf)
and generating normalized acoustic waterfall rasters.
"""

import json
import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

import cv2
from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.schemas.common import ErrorResponse
from app.schemas.sonar import (
    SonarInspectResponse,
    SonarNavigation,
)
from app.sonar.base import (
    BaseSonarParser,
    SonarParserError,
)
from app.sonar.jsf_reader import JsfSonarParser
from app.sonar.xtf_reader import XtfSonarParser

logger = logging.getLogger("marinescan.api.sonar")

router = APIRouter()


@contextmanager
def save_upload_to_temp(upload_file: UploadFile, suffix: str) -> Generator[Path, None, None]:
    """
    Safely stream an UploadFile to a temporary file on disk.
    Guarantees cleanup of the temporary file upon exit even if exceptions occur.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)
    try:
        tmp.close()
        upload_file.file.seek(0)
        with open(tmp_path, "wb") as f_out:
            while chunk := upload_file.file.read(1024 * 1024):  # 1MB stream buffer
                f_out.write(chunk)
        yield tmp_path
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception as exc:
                logger.warning("Could not unlink temporary file %s: %s", tmp_path, exc)


def select_parser(filename: Optional[str], file_path: Path) -> BaseSonarParser:
    """
    Select and validate the appropriate parser based on file extension and binary validation.
    Strictly prevents trusting the extension alone.
    """
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing filename: cannot determine sonar format.",
        )

    suffix = Path(filename).suffix.lower()

    if suffix == ".xtf":
        parser = XtfSonarParser()
        if not parser.validate(file_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file '{filename}' has .xtf extension but failed XTF format validation.",
            )
        return parser
    elif suffix == ".jsf":
        parser = JsfSonarParser()
        if not parser.validate(file_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file '{filename}' has .jsf extension but failed JSF format validation.",
            )
        return parser
    else:
        # Check if content matches either format despite non-standard extension
        xtf_parser = XtfSonarParser()
        if xtf_parser.validate(file_path):
            return xtf_parser
        jsf_parser = JsfSonarParser()
        if jsf_parser.validate(file_path):
            return jsf_parser

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format for '{filename}'. Only .xtf and .jsf files are supported.",
        )


HTTP_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


def parse_channels_param(channels: Optional[List[str]]) -> Optional[List[int]]:
    """
    Parse query parameter channels, handling both list format and comma-separated strings.
    """
    if not channels:
        return None

    parsed: List[int] = []
    for item in channels:
        for part in str(item).split(","):
            s = part.strip()
            if s:
                try:
                    val = int(s)
                    if val < 0:
                        raise HTTPException(
                            status_code=HTTP_422,
                            detail=f"Channel ID must be non-negative, got {val}.",
                        )
                    parsed.append(val)
                except ValueError:
                    raise HTTPException(
                        status_code=HTTP_422,
                        detail=f"Invalid channel ID: '{s}'. Must be an integer.",
                    )
    return parsed if parsed else None


@router.post(
    "/inspect",
    response_model=SonarInspectResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid, corrupt, or unsupported sonar recording"},
        422: {"model": ErrorResponse, "description": "Unprocessable upload request"},
        500: {"model": ErrorResponse, "description": "Internal parsing failure"},
    },
    summary="Inspect Raw Sonar Recording Header & Metadata",
    description="Upload an EdgeTech (.jsf) or Extended Triton (.xtf) sonar recording to extract format metadata, channels, and telemetry without generating acoustic sample arrays.",
)
async def inspect_sonar_file(
    file: UploadFile = File(..., description="Raw sonar recording (.xtf or .jsf)"),
) -> SonarInspectResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload.",
        )

    suffix = Path(file.filename).suffix.lower()
    with save_upload_to_temp(file, suffix) as tmp_path:
        if tmp_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        try:
            parser = select_parser(file.filename, tmp_path)
            header_meta = parser.parse_header(tmp_path)
            telemetry = parser.extract_telemetry(tmp_path)

            return SonarInspectResponse(
                filename=file.filename,
                format=header_meta.format,
                file_size_bytes=header_meta.file_size_bytes,
                total_pings=header_meta.total_pings,
                channel_count=header_meta.channel_count,
                channels=header_meta.channels,
                navigation_available=header_meta.navigation_available,
                telemetry=telemetry,
                warnings=header_meta.warnings,
                errors=[],
            )
        except HTTPException:
            raise
        except SonarParserError as spe:
            logger.warning("Sonar parsing rejected file '%s': %s", file.filename, spe)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sonar format or file corruption error: {str(spe)}",
            )
        except Exception as exc:
            logger.exception("Unexpected error inspecting sonar file '%s': %s", file.filename, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred while parsing the sonar file.",
            )


@router.post(
    "/raster",
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Normalized acoustic waterfall raster image (PNG).",
        },
        400: {"model": ErrorResponse, "description": "Invalid, corrupt, or unsupported sonar recording"},
        422: {"model": ErrorResponse, "description": "Invalid rendering parameters"},
        500: {"model": ErrorResponse, "description": "Raster assembly failure"},
    },
    summary="Generate Normalized Acoustic Waterfall Raster",
    description="Upload an EdgeTech (.jsf) or Extended Triton (.xtf) sonar recording and generate an aligned, normalized 2D acoustic waterfall image in PNG format.",
)
async def render_sonar_raster(
    file: UploadFile = File(..., description="Raw sonar recording (.xtf or .jsf)"),
    max_pings: Optional[int] = Query(None, ge=1, description="Maximum number of pings to render along-track"),
    channels: Optional[List[str]] = Query(None, description="Channels to render (e.g. ['0'], ['1'], or ['0,1'])"),
) -> Response:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in upload.",
        )

    parsed_channels = parse_channels_param(channels)
    suffix = Path(file.filename).suffix.lower()

    with save_upload_to_temp(file, suffix) as tmp_path:
        if tmp_path.stat().st_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        try:
            parser = select_parser(file.filename, tmp_path)
            raster, meta = parser.build_waterfall_raster(
                tmp_path,
                max_pings=max_pings,
                channels=parsed_channels,
            )

            if raster.size == 0 or raster.shape[0] == 0 or raster.shape[1] == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Sonar file contains no valid acoustic pings or channels to generate a waterfall raster.",
                )

            success, encoded = cv2.imencode(".png", raster)
            if not success or encoded is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to encode acoustic raster into PNG format.",
                )

            headers = {
                "Content-Type": "image/png",
                "X-Raster-Width": str(raster.shape[1]),
                "X-Raster-Height": str(raster.shape[0]),
                "X-Channel-Layout": str(meta.get("channel_layout", "unknown")),
                "X-Total-Pings": str(meta.get("total_pings", raster.shape[0])),
                "X-Sonar-Format": str(meta.get("format", "UNKNOWN")),
            }

            if meta.get("nadir_pixel_x") is not None:
                headers["X-Nadir-Pixel-X"] = f"{meta['nadir_pixel_x']:.1f}"
            else:
                headers["X-Nadir-Pixel-X"] = "null"

            if meta.get("meters_per_pixel") is not None:
                headers["X-Meters-Per-Pixel"] = f"{meta['meters_per_pixel']:.6f}"
            else:
                headers["X-Meters-Per-Pixel"] = "null"

            if meta.get("slant_range_m") is not None:
                headers["X-Slant-Range-M"] = f"{meta['slant_range_m']:.2f}"
            else:
                headers["X-Slant-Range-M"] = "null"

            json_meta = {
                "width": raster.shape[1],
                "height": raster.shape[0],
                "channel_layout": meta.get("channel_layout"),
                "nadir_pixel_x": meta.get("nadir_pixel_x"),
                "meters_per_pixel": meta.get("meters_per_pixel"),
                "slant_range_m": meta.get("slant_range_m"),
                "total_pings": meta.get("total_pings", raster.shape[0]),
                "channels_included": meta.get("channels_included", []),
                "format": meta.get("format"),
                "warnings": meta.get("warnings", []),
            }
            headers["X-Sonar-Metadata"] = json.dumps(json_meta)

            return Response(
                content=encoded.tobytes(),
                media_type="image/png",
                headers=headers,
            )

        except HTTPException:
            raise
        except SonarParserError as spe:
            logger.warning("Sonar parsing rejected file '%s': %s", file.filename, spe)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sonar format or file corruption error: {str(spe)}",
            )
        except ValueError as ve:
            logger.warning("Invalid raster parameters for '%s': %s", file.filename, ve)
            raise HTTPException(
                status_code=HTTP_422,
                detail=str(ve),
            )
        except Exception as exc:
            logger.exception("Unexpected error rendering sonar raster '%s': %s", file.filename, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred while generating the waterfall raster.",
            )
