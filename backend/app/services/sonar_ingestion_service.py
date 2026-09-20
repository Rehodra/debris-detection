"""
Raw Sonar Ingestion and Adapter Service for MarineScan.
Adapts raw sidescan sonar binary files (.xtf, .jsf) into standardized 3-channel BGR
NumPy imagery for consumption by the 12-stage Master Analysis Pipeline.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.schemas.analysis import SonarMetadataContext
from app.schemas.detection import ImageMetadata
from app.schemas.sonar import SonarNavigation, SonarNavigationTrack
from app.services.input_service import InputValidationError
from app.sonar.base import BaseSonarParser, SonarParserError
from app.sonar.jsf_reader import JSF_MAGIC_MARKER, JsfSonarParser
from app.sonar.xtf_reader import XTF_HEADER_SONAR, XTF_MAGIC_BYTE, XtfSonarParser

logger = logging.getLogger("marinescan.services.sonar_ingestion")

MIN_PIPELINE_DIMENSION_PX = 32


class SonarIngestionError(InputValidationError):
    """Raised when a raw sonar file cannot be ingested or converted to raster."""
    pass


@dataclass
class SonarIngestionResult:
    """
    Standardized result payload produced by the Sonar Ingestion Service.
    Provides the 3-channel BGR acoustic image and normalized provenance metadata.
    """
    image_bgr: np.ndarray
    image_metadata: ImageMetadata
    sonar_context: SonarMetadataContext
    nadir_pixel_x: Optional[float] = None
    meters_per_pixel: Optional[float] = None
    slant_range_m: Optional[float] = None
    navigation: Optional[SonarNavigation] = None
    waterfall_raster: Optional[np.ndarray] = None
    navigation_track: Optional[SonarNavigationTrack] = None



class SonarIngestionService:
    """
    Ingestion adapter translating raw XTF / JSF binary recordings into
    standardized BGR imagery for downstream detection, shadow, and risk analysis.
    """

    def __init__(self):
        self.xtf_parser = XtfSonarParser()
        self.jsf_parser = JsfSonarParser()

    def is_sonar_file(self, data: bytes, filename: Optional[str] = None) -> bool:
        """
        Determine whether the provided binary data is an XTF or JSF raw sonar recording.
        Inspects filename extension if provided, followed by binary header validation.
        """
        if not data or len(data) < 16:
            return False

        if filename:
            suffix = Path(filename).suffix.lower()
            if suffix == ".xtf":
                return self.xtf_parser.validate(data)
            elif suffix == ".jsf":
                return self.jsf_parser.validate(data)

        # Content-based detection if filename is absent or ambiguous
        # XTF magic byte: 0x7B and header type 0
        if len(data) >= 2 and data[0] == XTF_MAGIC_BYTE and data[1] == XTF_HEADER_SONAR:
            if self.xtf_parser.validate(data):
                return True

        # JSF magic marker: 0x1601 (bytes: \x01\x16 in little-endian)
        if len(data) >= 2 and int.from_bytes(data[:2], byteorder="little") == JSF_MAGIC_MARKER:
            if self.jsf_parser.validate(data):
                return True

        return False

    def select_parser(self, data: bytes, filename: Optional[str] = None) -> BaseSonarParser:
        """
        Select the appropriate parser for the sonar stream and validate format integrity.
        """
        if filename:
            suffix = Path(filename).suffix.lower()
            if suffix == ".xtf":
                if not self.xtf_parser.validate(data):
                    raise SonarIngestionError(f"File '{filename}' has .xtf extension but failed XTF format validation.")
                return self.xtf_parser
            elif suffix == ".jsf":
                if not self.jsf_parser.validate(data):
                    raise SonarIngestionError(f"File '{filename}' has .jsf extension but failed JSF format validation.")
                return self.jsf_parser

        # Fallback to binary signature inspection
        if self.xtf_parser.validate(data):
            return self.xtf_parser
        if self.jsf_parser.validate(data):
            return self.jsf_parser

        name_str = f"'{filename}'" if filename else "provided data"
        raise SonarIngestionError(
            f"Unsupported or invalid raw sonar recording for {name_str}. "
            "Supported formats: .xtf (Extended Triton) and .jsf (EdgeTech)."
        )

    def ingest_sonar(
        self,
        image_bytes: bytes,
        filename: Optional[str] = None,
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> SonarIngestionResult:
        """
        Execute raw sonar decoding and convert the normalized acoustic waterfall
        into a 3-channel BGR numpy matrix suitable for the MarineScan image pipeline.
        """
        if not image_bytes or len(image_bytes) == 0:
            raise SonarIngestionError("Uploaded sonar file is empty (0 bytes).")

        try:
            parser = self.select_parser(image_bytes, filename=filename)
            header_meta = parser.parse_header(image_bytes)
            telemetry = parser.extract_telemetry(image_bytes)
            raster, raster_meta = parser.build_waterfall_raster(
                image_bytes,
                max_pings=max_pings,
                channels=channels,
            )
            # Parse sequential ping-level telemetry track matching the exact max_pings window
            pings = parser.parse_pings(image_bytes, max_pings=max_pings)
        except SonarParserError as spe:
            logger.warning("Sonar parsing failed for '%s': %s", filename, spe)
            raise SonarIngestionError(f"Raw sonar decoding error: {str(spe)}") from spe
        except Exception as exc:
            logger.exception("Unexpected error parsing sonar file '%s': %s", filename, exc)
            raise SonarIngestionError(f"Failed to decode sonar recording: {str(exc)}") from exc

        if raster.size == 0 or raster.shape[0] == 0 or raster.shape[1] == 0:
            raise SonarIngestionError(
                f"Sonar file '{filename or 'unknown'}' contains no valid acoustic pings or samples."
            )

        orig_h, orig_w = raster.shape

        # Construct ordered navigation track
        valid_nav_pings = sum(
            1 for p in pings if p.latitude is not None and p.longitude is not None
        )
        navigation_track = SonarNavigationTrack(
            analysis_id=None,
            source_format=header_meta.format,
            total_pings=len(pings),
            available_navigation_pings=valid_nav_pings,
            points=pings,
            warnings=[],
        )

        # Downstream filters (e.g. Laplacian / Gaussian blur in quality check) require >= 32px
        # If along-track pings or cross-track bins are small, pad with edge replication
        if orig_h < MIN_PIPELINE_DIMENSION_PX or orig_w < MIN_PIPELINE_DIMENSION_PX:
            pad_h = max(0, MIN_PIPELINE_DIMENSION_PX - orig_h)
            pad_w = max(0, MIN_PIPELINE_DIMENSION_PX - orig_w)
            processed_raster = np.pad(raster, ((0, pad_h), (0, pad_w)), mode="edge")
        else:
            processed_raster = raster

        # Convert normalized 1-channel uint8 waterfall to standard 3-channel BGR
        image_bgr = cv2.cvtColor(processed_raster, cv2.COLOR_GRAY2BGR)
        h, w = image_bgr.shape[:2]

        # Assemble sonar context
        combined_warnings = list(header_meta.warnings)
        for rw in raster_meta.get("warnings", []):
            if rw not in combined_warnings:
                combined_warnings.append(rw)

        sonar_context = SonarMetadataContext(
            format=header_meta.format,
            filename=filename or header_meta.filename,
            total_pings=header_meta.total_pings,
            channel_count=header_meta.channel_count,
            channels_included=raster_meta.get("channels_included", []),
            waterfall_width=orig_w,
            waterfall_height=orig_h,
            channel_layout=raster_meta.get("channel_layout", "unknown"),
            nadir_pixel_x=raster_meta.get("nadir_pixel_x"),
            meters_per_pixel=raster_meta.get("meters_per_pixel"),
            slant_range_m=raster_meta.get("slant_range_m"),
            navigation=telemetry,
            warnings=combined_warnings,
        )

        image_metadata = ImageMetadata(
            width=w,
            height=h,
            channels=3,
            format=header_meta.format,
        )

        return SonarIngestionResult(
            image_bgr=image_bgr,
            image_metadata=image_metadata,
            sonar_context=sonar_context,
            nadir_pixel_x=raster_meta.get("nadir_pixel_x"),
            meters_per_pixel=raster_meta.get("meters_per_pixel"),
            slant_range_m=raster_meta.get("slant_range_m"),
            navigation=telemetry,
            waterfall_raster=raster,
            navigation_track=navigation_track,
        )


# Global service instance
sonar_ingestion_service = SonarIngestionService()
