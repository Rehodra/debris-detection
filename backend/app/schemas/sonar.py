"""
Pydantic schemas for Raw Sonar Ingestion, Metadata, Telemetry, and Parsed Streams.
Supports Extended Triton Format (.xtf) and EdgeTech JSF (.jsf) normalized structures.
"""

from typing import List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, computed_field, model_validator


class SonarFormat(str, Enum):
    """Supported raw sonar binary formats."""
    XTF = "XTF"
    JSF = "JSF"
    UNKNOWN = "UNKNOWN"


class SonarNavigation(BaseModel):
    """
    Normalized vessel or sensor navigation fix extracted from raw sonar records.
    All fields that may legitimately be absent default strictly to None.
    """
    model_config = ConfigDict(extra="ignore")

    timestamp: Optional[str] = Field(None, description="ISO-8601 navigation timestamp or UTC string if recorded")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="WGS84 latitude in decimal degrees")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="WGS84 longitude in decimal degrees")
    heading_deg: Optional[float] = Field(None, ge=0.0, le=360.0, description="Vessel or towfish gyro heading in degrees true")
    altitude_m: Optional[float] = Field(None, ge=0.0, description="Towfish altitude above seabed in meters")
    depth_m: Optional[float] = Field(None, ge=0.0, description="Towfish depth below water surface in meters")
    source: Optional[str] = Field(None, description="Origin of navigation fix (e.g., 'primary_nav', 'ping_header', 'attitude')")

    @model_validator(mode="before")
    @classmethod
    def _normalize_nav_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "heading" in data and "heading_deg" not in data:
                data["heading_deg"] = data.get("heading")
            if "altitude" in data and "altitude_m" not in data:
                data["altitude_m"] = data.get("altitude")
            if "depth" in data and "depth_m" not in data:
                data["depth_m"] = data.get("depth")
        return data

    @computed_field
    @property
    def heading(self) -> Optional[float]:
        """Normalized heading alias for heading_deg."""
        return self.heading_deg

    @computed_field
    @property
    def altitude(self) -> Optional[float]:
        """Normalized altitude alias for altitude_m."""
        return self.altitude_m

    @computed_field
    @property
    def depth(self) -> Optional[float]:
        """Normalized depth alias for depth_m."""
        return self.depth_m


class SonarChannelInfo(BaseModel):
    """
    Metadata for an acoustic sonar channel (e.g., Port, Starboard, High/Low Frequency).
    """
    model_config = ConfigDict(extra="ignore")

    channel_id: int = Field(..., description="Zero-based or protocol-based channel index")
    channel_name: str = Field(..., description="Channel name or descriptor, e.g., 'port', 'starboard', 'subbottom'")
    frequency_hz: Optional[float] = Field(None, ge=0.0, description="Operating acoustic center frequency in Hz")
    sample_count: Optional[int] = Field(None, ge=0, description="Nominal number of acoustic samples per ping for this channel")
    range_m: Optional[float] = Field(None, ge=0.0, description="Slant range extent in meters")
    sample_format: Optional[str] = Field(None, description="Data encoding format (e.g. 'uint8', 'uint16', 'int16', 'float32')")
    available: bool = Field(True, description="Whether this channel contains valid decodable acoustic samples")


class SonarPingTelemetry(BaseModel):
    """
    Per-ping navigation and sensor telemetry record.
    Missing navigation and altitude/depth fields strictly remain None.
    """
    model_config = ConfigDict(extra="ignore")

    ping_index: int = Field(..., ge=0, description="Sequential ping index in file")
    timestamp: Optional[str] = Field(None, description="Ping UTC timestamp string (ISO-8601 or epoch)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="WGS84 latitude in decimal degrees if logged")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="WGS84 longitude in decimal degrees if logged")
    heading_deg: Optional[float] = Field(None, ge=0.0, le=360.0, description="Heading in degrees true [0, 360]")
    altitude_m: Optional[float] = Field(None, ge=0.0, description="Towfish altitude off seafloor in meters")
    depth_m: Optional[float] = Field(None, ge=0.0, description="Sensor depth below sea surface in meters")
    source_format: Optional[str] = Field(None, description="Origin format identifier ('XTF' or 'JSF')")
    channel_id: Optional[int] = Field(None, description="Optional acoustic channel identifier")
    waterfall_row: Optional[int] = Field(None, ge=0, description="Corresponding scanline row index in the acoustic waterfall raster")

    @model_validator(mode="before")
    @classmethod
    def _normalize_ping_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "heading" in data and "heading_deg" not in data:
                data["heading_deg"] = data.get("heading")
            if "altitude" in data and "altitude_m" not in data:
                data["altitude_m"] = data.get("altitude")
            if "depth" in data and "depth_m" not in data:
                data["depth_m"] = data.get("depth")
            if ("waterfall_row" not in data or data.get("waterfall_row") is None) and "ping_index" in data:
                data["waterfall_row"] = data.get("ping_index")
        return data

    @computed_field
    @property
    def heading(self) -> Optional[float]:
        """Normalized heading alias for heading_deg."""
        return self.heading_deg

    @computed_field
    @property
    def altitude(self) -> Optional[float]:
        """Normalized altitude alias for altitude_m."""
        return self.altitude_m

    @computed_field
    @property
    def depth(self) -> Optional[float]:
        """Normalized depth alias for depth_m."""
        return self.depth_m


class SonarNavigationTrack(BaseModel):
    """
    Ordered ping-level navigation track representing the actual sonar acquisition path.
    Preserves acquisition order (ping_index ascending).
    """
    model_config = ConfigDict(extra="ignore")

    analysis_id: Optional[str] = Field(None, description="Associated mission or analysis identifier")
    source_format: str = Field(..., description="Raw sonar format ('XTF' or 'JSF')")
    total_pings: int = Field(..., ge=0, description="Total pings in this track segment")
    available_navigation_pings: int = Field(..., ge=0, description="Number of pings containing valid geographic coordinates")
    points: List[SonarPingTelemetry] = Field(default_factory=list, description="Ordered ping-level telemetry points")
    warnings: List[str] = Field(default_factory=list, description="Track or navigation warnings")


class SonarFileMetadata(BaseModel):
    """
    Summary metadata for an ingested raw sonar file.
    """
    model_config = ConfigDict(extra="ignore")

    filename: str = Field(..., description="Original name of the ingested file")
    format: str = Field(..., description="Identified format string (e.g. 'XTF', 'JSF')")
    file_size_bytes: int = Field(..., ge=0, description="File size in bytes")
    total_pings: int = Field(..., ge=0, description="Total number of acoustic pings recorded in file")
    channel_count: int = Field(..., ge=0, description="Number of acoustic channels present")
    channels: List[SonarChannelInfo] = Field(default_factory=list, description="Detailed per-channel metadata")
    navigation_available: bool = Field(False, description="True if any valid non-null GPS navigation coordinates were recovered")
    warnings: List[str] = Field(default_factory=list, description="Parsing warnings, skipped packets, or data anomalies")


class SonarParseResult(BaseModel):
    """
    Complete payload produced by a sonar parser.
    """
    model_config = ConfigDict(extra="ignore")

    metadata: SonarFileMetadata = Field(..., description="File and channel metadata")
    navigation: Optional[SonarNavigation] = Field(None, description="Primary or survey-origin navigation fix")
    pings: List[SonarPingTelemetry] = Field(default_factory=list, description="Per-ping telemetry stream")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings encountered during parsing")
    errors: List[str] = Field(default_factory=list, description="Recoverable or non-fatal parsing errors logged during execution")


class SonarInspectResponse(BaseModel):
    """
    Response schema for POST /api/v1/sonar/inspect endpoint.
    Exposes file metadata, channel descriptors, and representative navigation fix without acoustic samples.
    """
    model_config = ConfigDict(extra="ignore")

    filename: str = Field(..., description="Original name of the ingested raw sonar recording")
    format: str = Field(..., description="Identified format string (e.g. 'XTF', 'JSF')")
    file_size_bytes: int = Field(..., ge=0, description="File size in bytes")
    total_pings: int = Field(..., ge=0, description="Total number of acoustic pings recorded in file")
    channel_count: int = Field(..., ge=0, description="Number of acoustic channels present")
    channels: List[SonarChannelInfo] = Field(default_factory=list, description="Detailed per-channel metadata")
    navigation_available: bool = Field(False, description="True if valid geodetic GPS coordinates were recovered")
    telemetry: Optional[SonarNavigation] = Field(None, description="First valid / representative navigation fix")
    warnings: List[str] = Field(default_factory=list, description="Parsing warnings, skipped packets, or data anomalies")
    errors: List[str] = Field(default_factory=list, description="Non-fatal errors encountered during ingestion")


class SonarTargetGeoreference(BaseModel):
    """
    Geospatial correlation linking a detected target on a sonar waterfall raster
    to its source ping telemetry, across-track physical offset, and WGS84 geographic position.
    """
    model_config = ConfigDict(extra="ignore")

    status: str = Field(..., description="Correlation status: 'calculated', 'unavailable_missing_nav', 'unavailable_missing_gsd'")
    coordinate_reference: str = Field("WGS84", description="Geodetic datum reference (strictly WGS84)")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Calculated WGS84 latitude in decimal degrees")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Calculated WGS84 longitude in decimal degrees")
    source_ping_index: int = Field(..., ge=0, description="Sequential ping index in file corresponding to detection centroid")
    waterfall_row: int = Field(..., ge=0, description="Waterfall raster scanline row corresponding to detection centroid")
    across_track_pixel: float = Field(..., description="Target centroid horizontal pixel coordinate in raster")
    across_track_offset_m: Optional[float] = Field(None, description="Metric offset perpendicular to heading (+ starboard, - port)")
    slant_range_m: Optional[float] = Field(None, ge=0.0, description="Recorded slant range extent if available")
    heading_deg: Optional[float] = Field(None, ge=0.0, le=360.0, description="Sensor/vessel true heading in degrees used for projection")
    layback_applied: bool = Field(False, description="Whether towfish catenary layback correction was applied")
    layback_distance_m: Optional[float] = Field(None, description="Horizontal layback distance in meters behind vessel if applied")
    vessel_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Surface vessel latitude at ping time")
    vessel_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Surface vessel longitude at ping time")
    sensor_latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Towfish/sensor latitude at ping time")
    sensor_longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Towfish/sensor longitude at ping time")
    warnings: List[str] = Field(default_factory=list, description="Telemetry, resolution, or geometry correlation warnings")


