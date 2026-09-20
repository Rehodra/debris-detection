"""
MarineScan Raw Sonar Processing Package.
Provides format decoders, telemetry extractors, and waterfall raster builders
for raw sidescan sonar formats (.xtf, .jsf).
"""

from app.sonar.base import (
    BaseSonarParser,
    SonarParserError,
    SonarFormatError,
    SonarCorruptFileError,
    SonarNavigationError,
    open_binary_source,
)
from app.sonar.xtf_reader import XtfSonarParser
from app.sonar.jsf_reader import JsfSonarParser
from app.sonar.raster_reader import SonarRasterBuilder

__all__ = [
    "BaseSonarParser",
    "XtfSonarParser",
    "JsfSonarParser",
    "SonarRasterBuilder",
    "SonarParserError",
    "SonarFormatError",
    "SonarCorruptFileError",
    "SonarNavigationError",
    "open_binary_source",
]
