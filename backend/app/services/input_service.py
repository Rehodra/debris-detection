"""
Input Validation and Ingestion Service for MarineScan.
Handles Stage 1 of the Master Pipeline:
Verifies file integrity, MIME magic byte signatures, dimension sanity,
and safely decodes raw image bytes into standardized BGR NumPy arrays.
"""

import logging
from typing import Tuple
import cv2
import numpy as np

from app.schemas.detection import ImageMetadata

logger = logging.getLogger("marinescan.services.input")

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB max
MIN_DIMENSION_PX = 32
MAX_DIMENSION_PX = 12000


class InputValidationError(ValueError):
    """Raised when an uploaded file fails validation or decoding."""
    pass


class InputService:
    """Robust image file validation, format detection, and safe decoding engine."""

    MAGIC_SIGNATURES = {
        b"\xff\xd8\xff": "JPEG",
        b"\x89PNG\r\n\x1a\n": "PNG",
        b"RIFF": "WEBP",
        b"BM": "BMP",
        b"II*\x00": "TIFF",
        b"MM\x00*": "TIFF",
    }

    def detect_format(self, data: bytes) -> str:
        """Detect image format by inspecting file header magic bytes."""
        if len(data) < 8:
            return "UNKNOWN"

        if data.startswith(b"\xff\xd8\xff"):
            return "JPEG"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG"
        if data.startswith(b"BM"):
            return "BMP"
        if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
            return "TIFF"
        if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
            return "WEBP"

        return "UNKNOWN"

    def validate_and_decode(self, image_bytes: bytes) -> Tuple[np.ndarray, ImageMetadata]:
        """
        Execute comprehensive Stage 1 validation and decode into BGR image.
        """
        if not image_bytes or len(image_bytes) == 0:
            raise InputValidationError("Uploaded file is empty (0 bytes).")

        if len(image_bytes) > MAX_FILE_SIZE_BYTES:
            mb_size = len(image_bytes) / (1024 * 1024)
            raise InputValidationError(f"Uploaded file exceeds 100MB limit ({mb_size:.1f} MB).")

        detected_fmt = self.detect_format(image_bytes)
        if detected_fmt == "UNKNOWN":
            logger.warning("Unrecognized file signature; attempting OpenCV decode anyway.")

        np_arr = np.frombuffer(image_bytes, np.uint8)
        img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img_bgr is None:
            raise InputValidationError(
                "Could not decode image from provided data. "
                "Supported formats: JPEG, PNG, WEBP, BMP, TIFF."
            )

        h, w = img_bgr.shape[:2]
        if w < MIN_DIMENSION_PX or h < MIN_DIMENSION_PX:
            raise InputValidationError(
                f"Image dimensions ({w}x{h}) are smaller than minimum allowed ({MIN_DIMENSION_PX}x{MIN_DIMENSION_PX})."
            )

        if w > MAX_DIMENSION_PX or h > MAX_DIMENSION_PX:
            raise InputValidationError(
                f"Image dimensions ({w}x{h}) exceed maximum allowed ({MAX_DIMENSION_PX}x{MAX_DIMENSION_PX})."
            )

        metadata = ImageMetadata(
            width=w,
            height=h,
            channels=3,
            format=detected_fmt if detected_fmt != "UNKNOWN" else "JPEG",
        )
        return img_bgr, metadata


# Global service instance
input_service = InputService()
