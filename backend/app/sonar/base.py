"""
Abstract Parser Contract and Base Classes for MarineScan Sonar Ingestion.
Defines the uniform interface for sidescan and subsea sonar recording formats (.xtf, .jsf).
"""

import io
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Dict, Any, Generator, List, Optional, Tuple, Union

import numpy as np

from app.schemas.sonar import (
    SonarFileMetadata,
    SonarNavigation,
    SonarParseResult,
    SonarPingTelemetry,
)


class SonarParserError(Exception):
    """Base exception for all sonar parsing errors."""
    pass


class SonarFormatError(SonarParserError):
    """Raised when file signature, magic bytes, or framing do not match the expected format."""
    pass


class SonarCorruptFileError(SonarParserError):
    """Raised when binary packet structure is truncated, malformed, or contains invalid lengths."""
    pass


class SonarNavigationError(SonarParserError):
    """Raised when navigational records are structurally unparseable or severely malformed."""
    pass


@contextmanager
def open_binary_source(source: Union[str, Path, BinaryIO, bytes]) -> Generator[BinaryIO, None, None]:
    """
    Context manager that yields a seekable binary stream from:
      - File path (str or Path)
      - Raw bytes (wrapped in io.BytesIO)
      - An already open BinaryIO stream

    If a path or bytes are provided, the stream is opened and closed within the context.
    If an existing stream is passed, it is yielded without closing.
    """
    if isinstance(source, (str, Path)):
        with open(source, "rb") as stream:
            yield stream
    elif isinstance(source, bytes):
        stream = io.BytesIO(source)
        try:
            yield stream
        finally:
            stream.close()
    elif hasattr(source, "read"):
        yield source
    else:
        raise TypeError(f"Unsupported source type for sonar reader: {type(source).__name__}")


class BaseSonarParser(ABC):
    """
    Abstract base parser contract for raw sonar recording formats.

    Establishes the standard ingestion pipeline across formats:
      1. validate(): Fast header signature/magic byte verification.
      2. parse_header(): Channel descriptors, recording system info, and file parameters.
      3. parse_pings(): Sequential acoustic ping telemetry stream extraction.
      4. extract_telemetry(): Primary or survey-origin navigation fix.
      5. build_waterfall_raster(): Assembles acoustic intensity channels into a 2D/3D NumPy raster.

    Concrete implementations (XTFParser, JSFParser) implement these methods
    according to their specific binary specifications without sharing incorrect binary assumptions.
    """

    @abstractmethod
    def validate(self, source: Union[str, Path, BinaryIO, bytes]) -> bool:
        """
        Verify whether the given source matches this parser's binary signature and format.

        Args:
            source: File path, open binary stream, or raw byte buffer.

        Returns:
            True if the source is a valid file for this parser, False otherwise.
        """
        pass

    @abstractmethod
    def parse_header(self, source: Union[str, Path, BinaryIO, bytes]) -> SonarFileMetadata:
        """
        Parse file-level headers and extract channel descriptors and recording parameters.

        Args:
            source: File path, open binary stream, or raw byte buffer.

        Returns:
            SonarFileMetadata containing file structure, channel list, and initial indicators.

        Raises:
            SonarFormatError: If file header signature does not match.
            SonarCorruptFileError: If header data is truncated or unreadable.
        """
        pass

    @abstractmethod
    def parse_pings(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
    ) -> List[SonarPingTelemetry]:
        """
        Parse sequential acoustic ping records and extract per-ping navigation/sensor telemetry.

        Args:
            source: File path, open binary stream, or raw byte buffer.
            max_pings: Optional limit on the number of pings to parse.

        Returns:
            List of SonarPingTelemetry records. Missing sensor fields remain None.

        Raises:
            SonarCorruptFileError: If ping packets cannot be unpacked.
        """
        pass

    @abstractmethod
    def extract_telemetry(self, source: Union[str, Path, BinaryIO, bytes]) -> Optional[SonarNavigation]:
        """
        Extract primary or representative survey navigation fix from the file.

        Args:
            source: File path, open binary stream, or raw byte buffer.

        Returns:
            SonarNavigation with coordinates and heading if available, or None if no valid fix exists.
        """
        pass

    @abstractmethod
    def build_waterfall_raster(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
        channels: Optional[List[int]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Assemble raw acoustic ping channels into a 2D or 3D NumPy array (waterfall raster)
        suitable for acoustic enhancement and downstream YOLO inference.

        Args:
            source: File path, open binary stream, or raw byte buffer.
            max_pings: Optional limit on the number of pings to render.
            channels: Optional list of channel indices to include (e.g. Port, Starboard).

        Returns:
            Tuple of:
              - np.ndarray: Acoustic intensity matrix (e.g. HxW uint8 or float32).
              - Dict[str, Any]: Spatial & rendering metadata (e.g. nadir_pixel_x, meters_per_pixel, port_range_m, stbd_range_m).

        Raises:
            SonarCorruptFileError: If acoustic sample data is corrupted or truncated.
        """
        pass

    def parse(
        self,
        source: Union[str, Path, BinaryIO, bytes],
        max_pings: Optional[int] = None,
    ) -> SonarParseResult:
        """
        High-level convenience method executing header extraction, telemetry aggregation,
        and ping parsing.

        Args:
            source: File path, open binary stream, or raw byte buffer.
            max_pings: Optional limit on the number of pings to parse.

        Returns:
            SonarParseResult containing metadata, navigation fix, pings telemetry, and any warnings.
        """
        metadata = self.parse_header(source)
        navigation = self.extract_telemetry(source)
        pings = self.parse_pings(source, max_pings=max_pings)
        return SonarParseResult(
            metadata=metadata,
            navigation=navigation,
            pings=pings,
            warnings=list(metadata.warnings),
            errors=[],
        )
