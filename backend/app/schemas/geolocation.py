"""
Pydantic schemas for Marine Debris Geolocation, Geodesy, and Navigation.
Models vessel/sensor navigation fixes, towfish layback configurations,
WGS84 and UTM coordinates, DMS string formatting, and standard RFC 7946 GeoJSON.
"""

from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel, Field


class NavigationalFix(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude in decimal degrees")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude in decimal degrees")
    heading_degrees: float = Field(..., ge=0.0, le=360.0, description="Vessel or sensor gyro heading in degrees true (0 = North, 90 = East)")
    speed_knots: Optional[float] = Field(None, ge=0.0, description="Vehicle speed over ground in knots")
    altitude_or_depth_m: Optional[float] = Field(None, description="Sensor altitude off seafloor or depth below surface (m)")
    timestamp: Optional[str] = Field(None, description="ISO8601 navigation timestamp")


class TowfishConfig(BaseModel):
    cable_payout_m: float = Field(..., gt=0.0, description="Length of umbilical/tow cable deployed from vessel (m)")
    fish_depth_m: float = Field(..., ge=0.0, description="Depth of towfish below surface (m)")
    catenary_factor: float = Field(0.95, ge=0.7, le=1.0, description="Cable catenary curvature correction factor (default: 0.95)")
    computed_layback_m: Optional[float] = Field(None, description="Computed horizontal layback distance behind vessel (m)")


class SonarScanOrigin(BaseModel):
    nadir_pixel_x: float = Field(..., description="Pixel X column of the sonar nadir / central ground-track line")
    reference_pixel_y: float = Field(0.0, description="Reference scan line row index corresponding to the NavigationalFix")
    across_track_gsd_m: float = Field(0.05, gt=0.0, description="Across-track ground sampling distance (meters/pixel)")
    along_track_gsd_m: float = Field(0.05, gt=0.0, description="Along-track ground sampling distance (meters/pixel)")


class GeoCoordinates(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Decimal latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Decimal longitude")
    dms_string: str = Field(..., description="Nautical Degrees Minutes Seconds formatted string (e.g. 24° 51' 38.6\" N, 067° 00' 04.1\" E)")
    utm_zone: str = Field(..., description="Universal Transverse Mercator Zone (e.g. '42N')")
    utm_easting_m: float = Field(..., description="UTM Easting in meters")
    utm_northing_m: float = Field(..., description="UTM Northing in meters")
    depth_m: Optional[float] = Field(None, description="Target seabed depth in meters")


class GeolocatedTarget(BaseModel):
    target_id: str = Field(..., description="Detection or target identifier")
    class_name: str = Field(..., description="Debris class (shipwreck, aircraft, fish, other)")
    confidence: float = Field(..., description="Detection confidence")
    pixel_centroid: Tuple[float, float] = Field(..., description="Target centroid in image pixel coordinates (x, y)")
    across_track_offset_m: float = Field(..., description="Offset perpendicular to heading (+ starboard, - port) in meters")
    along_track_offset_m: float = Field(..., description="Offset along heading (+ forward, - astern) in meters")
    coordinates: GeoCoordinates = Field(..., description="Calculated geographic coordinates")
    distance_from_sensor_m: float = Field(..., description="Straight-line horizontal distance from sensor/vessel (m)")
    bearing_degrees: float = Field(..., description="True bearing from sensor/vessel to target in degrees [0 - 360)")


class GeoJSONGeometry(BaseModel):
    type: str = Field("Point", description="GeoJSON geometry type")
    coordinates: List[float] = Field(..., description="[longitude, latitude, optional elevation]")


class GeoJSONFeature(BaseModel):
    type: str = Field("Feature", description="GeoJSON type")
    geometry: GeoJSONGeometry = Field(..., description="Point geometry")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Target properties, class, confidence, and metrics")


class GeoJSONFeatureCollection(BaseModel):
    type: str = Field("FeatureCollection", description="GeoJSON type")
    features: List[GeoJSONFeature] = Field(default_factory=list, description="List of target features")


class BatchGeolocationResponse(BaseModel):
    status: str = Field("success", description="Execution status")
    total_targets_geolocated: int = Field(..., description="Total targets successfully positioned")
    sensor_position: GeoCoordinates = Field(..., description="Estimated sonar sensor position (after layback if applied)")
    vessel_position: Optional[GeoCoordinates] = Field(None, description="Surface vessel position if layback was used")
    targets: List[GeolocatedTarget] = Field(default_factory=list, description="Per-target geolocated profiles")
    geojson: GeoJSONFeatureCollection = Field(..., description="RFC 7946 GeoJSON FeatureCollection for map rendering")
