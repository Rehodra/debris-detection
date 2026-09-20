"""
Unit and integration tests for Phase 9: Detection-to-Geospatial Correlation & Target Georeferencing.

Validates:
1. Detection -> Raster Mapping:
   - center_x to across_track_pixel
   - center_y to waterfall_row (1:1 mapping)
   - row clamping to track bounds (no IndexError)
   - nadir pixel offset calculation
   - meters_per_pixel scaling
   - starboard offset positive sign
   - port offset negative sign
   - nadir centered offset zero

2. Ping Track Correlation:
   - ping_index matches waterfall_row
   - ordered track lookup of correct ping
   - missing navigation yields null coordinates
   - missing navigation status code
   - no (0, 0) coordinates fabricated
   - missing track handled gracefully
   - track with fewer pings than detections clamps safely

3. Geospatial Calculation:
   - deterministic WGS84 coordinates
   - heading 0 deg: starboard shifts East
   - heading 90 deg: starboard shifts South
   - heading 180 deg: starboard shifts West
   - heading 270 deg: starboard shifts North
   - towfish layback corrects sensor position astern
   - vessel and sensor coordinates distinct with layback
   - missing meters_per_pixel yields null coordinates with warning
   - coordinate_reference strictly "WGS84"

4. Pipeline Integration:
   - sonar detection receives populated georeference
   - multiple detections georeferenced independently
   - conventional camera image unaffected by sonar georef
   - sonar metadata track artifact associated

5. Hydrographic Exports:
   - GeoJSON target features have strictly [longitude, latitude]
   - GeoJSON omits targets without coordinates (no null or 0,0 points)
   - GeoJSON feature properties include georef metadata
   - CSV export includes georef columns (source_ping_index, waterfall_row, etc.)
   - CSV export handles null coordinates cleanly
   - JSON export is backward-compatible with georeference field

6. Regression Tests:
   - sonar waterfall raster retrieval still works
   - sonar track endpoint still works
   - hydrographic export endpoints still work
"""

import csv
import io
import json
import unittest
from typing import List, Optional, Tuple
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.detection import (
    BoundingBox,
    DetectionItem,
    DetectionResponse,
    DetectionSummary,
    ImageMetadata,
)
from app.schemas.geolocation import (
    GeoCoordinates,
    NavigationalFix,
    SonarScanOrigin,
    TowfishConfig,
)
from app.schemas.sonar import (
    SonarNavigationTrack,
    SonarPingTelemetry,
    SonarTargetGeoreference,
)
from app.services.geolocation_service import geolocation_service
from app.services.hydrographic_export_service import hydrographic_export_service
from app.services.master_pipeline_service import master_pipeline_service
from app.tests.test_sonar_track import build_custom_track_xtf
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


def make_mock_detection_response(detections_data: list, width: int = 128, height: int = 8) -> DetectionResponse:
    items = []
    for i, d in enumerate(detections_data):
        bbox_dict = d.get("bbox", {})
        x_min = float(bbox_dict.get("x_min", 0.0))
        y_min = float(bbox_dict.get("y_min", 0.0))
        w = float(bbox_dict.get("width", 10.0))
        h = float(bbox_dict.get("height", 10.0))
        item = DetectionItem(
            detection_id=d.get("detection_id", f"det_{i+1:02d}"),
            class_id=d.get("class_id", 1),
            class_name=d.get("class_name", "container"),
            display_name=d.get("display_name", "Shipping Container"),
            category=d.get("category", "Cargo Debris"),
            risk_level="High",
            confidence=float(d.get("confidence", 0.9)),
            bbox=BoundingBox(
                x_min=x_min,
                y_min=y_min,
                x_max=x_min + w,
                y_max=y_min + h,
                width=w,
                height=h,
                normalized_x_min=x_min / max(width, 1),
                normalized_y_min=y_min / max(height, 1),
                normalized_x_max=(x_min + w) / max(width, 1),
                normalized_y_max=(y_min + h) / max(height, 1),
            ),
            area_pixels=w * h,
            color_hex="#E76F51",
            color_rgb=[231, 111, 81],
        )
        items.append(item)

    return DetectionResponse(
        status="success",
        model_name="MarineScan Mock YOLO",
        device="cpu",
        inference_time_ms=10.0,
        total_time_ms=15.0,
        image_info=ImageMetadata(width=width, height=height, channels=3, format="PNG"),
        detections=items,
        summary=DetectionSummary(total_detections=len(items)),
    )


class TestDetectionRasterMapping(unittest.TestCase):
    """Unit tests validating detection bounding-box centroid mapping to waterfall raster geometry."""

    def setUp(self):
        self.pings = [
            SonarPingTelemetry(
                ping_index=i,
                timestamp=f"2026-09-18T12:00:{i:02d}Z",
                latitude=24.8607 + i * 0.0001,
                longitude=67.0011 + i * 0.0001,
                heading=90.0,
                altitude=10.0,
                depth=20.0,
            )
            for i in range(10)
        ]
        self.track = SonarNavigationTrack(
            analysis_id="test_mapping_msn",
            source_format="XTF",
            total_pings=10,
            available_navigation_pings=10,
            points=self.pings,
        )

    def test_detection_center_x_to_across_track_pixel(self):
        """Verify across_track_pixel is calculated from bbox centroid center_x."""
        detections = [
            {
                "detection_id": "det_01",
                "class_name": "container",
                "confidence": 0.95,
                "bbox": {"x_min": 100.0, "y_min": 50.0, "width": 40.0, "height": 30.0},
            }
        ]
        # center_x = 100.0 + 20.0 = 120.0
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections,
            navigation_track=self.track,
            nadir_pixel_x=100.0,
            meters_per_pixel=0.1,
        )
        self.assertEqual(len(res.targets), 1)
        georef = res.targets[0].georeference
        self.assertIsNotNone(georef)
        self.assertAlmostEqual(georef.across_track_pixel, 120.0)

    def test_detection_center_y_to_waterfall_row(self):
        """Verify waterfall_row and ping_index are mapped 1:1 from bbox center_y."""
        detections = [
            {
                "detection_id": "det_02",
                "class_name": "trawl_gear",
                "confidence": 0.88,
                "bbox": {"x_min": 60.0, "y_min": 4.6, "width": 20.0, "height": 0.8},
            }
        ]
        # center_y = 4.6 + 0.4 = 5.0 -> row 5
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections,
            navigation_track=self.track,
            nadir_pixel_x=100.0,
            meters_per_pixel=0.1,
        )
        georef = res.targets[0].georeference
        self.assertEqual(georef.waterfall_row, 5)
        self.assertEqual(georef.source_ping_index, 5)

    def test_row_clamping_to_track_bounds(self):
        """Verify centroid center_y outside track range safely clamps without IndexError."""
        detections = [
            {
                "detection_id": "det_high",
                "class_name": "pipe",
                "confidence": 0.85,
                "bbox": {"x_min": 50.0, "y_min": 900.0, "width": 10.0, "height": 10.0},
            },
            {
                "detection_id": "det_neg",
                "class_name": "drum",
                "confidence": 0.80,
                "bbox": {"x_min": 50.0, "y_min": -20.0, "width": 10.0, "height": 10.0},
            },
        ]
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections,
            navigation_track=self.track,  # 10 pings: valid indices 0..9
            nadir_pixel_x=100.0,
            meters_per_pixel=0.1,
        )
        self.assertEqual(len(res.targets), 2)
        # Bounded row for det_high should be 9
        self.assertEqual(res.targets[0].georeference.source_ping_index, 9)
        # Bounded row for det_neg should be 0
        self.assertEqual(res.targets[1].georeference.source_ping_index, 0)

    def test_nadir_pixel_offset_calculation(self):
        """Verify metric offset is (center_x - nadir_pixel_x) * meters_per_pixel."""
        detections = [
            {
                "detection_id": "det_sb",
                "bbox": {"x_min": 140.0, "y_min": 2.0, "width": 20.0, "height": 2.0},  # center_x = 150
            },
            {
                "detection_id": "det_port",
                "bbox": {"x_min": 70.0, "y_min": 2.0, "width": 20.0, "height": 2.0},  # center_x = 80
            },
        ]
        # nadir = 100.0, mpp = 0.2
        # det_sb offset = (150 - 100) * 0.2 = +10.0 m
        # det_port offset = (80 - 100) * 0.2 = -4.0 m
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections,
            navigation_track=self.track,
            nadir_pixel_x=100.0,
            meters_per_pixel=0.2,
        )
        self.assertAlmostEqual(res.targets[0].georeference.across_track_offset_m, 10.0)
        self.assertAlmostEqual(res.targets[1].georeference.across_track_offset_m, -4.0)

    def test_meters_per_pixel_scaling(self):
        """Verify metric distance scales proportionally with meters_per_pixel."""
        detections = [
            {
                "detection_id": "det_scale",
                "bbox": {"x_min": 190.0, "y_min": 0.0, "width": 20.0, "height": 2.0},  # center_x = 200
            }
        ]
        # nadir = 100.0 -> pixel offset = 100
        res_05 = geolocation_service.geolocate_sonar_detections(
            detections=detections, navigation_track=self.track, nadir_pixel_x=100.0, meters_per_pixel=0.05
        )
        res_20 = geolocation_service.geolocate_sonar_detections(
            detections=detections, navigation_track=self.track, nadir_pixel_x=100.0, meters_per_pixel=0.20
        )
        self.assertAlmostEqual(res_05.targets[0].georeference.across_track_offset_m, 5.0)
        self.assertAlmostEqual(res_20.targets[0].georeference.across_track_offset_m, 20.0)

    def test_starboard_offset_positive_sign(self):
        """Verify detections right of nadir have strictly positive across-track offset."""
        detections = [{"detection_id": "sb", "bbox": {"x_min": 120.0, "y_min": 0.0, "width": 10.0, "height": 10.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections, navigation_track=self.track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertGreater(res.targets[0].georeference.across_track_offset_m, 0.0)

    def test_port_offset_negative_sign(self):
        """Verify detections left of nadir have strictly negative across-track offset."""
        detections = [{"detection_id": "port", "bbox": {"x_min": 40.0, "y_min": 0.0, "width": 10.0, "height": 10.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections, navigation_track=self.track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertLess(res.targets[0].georeference.across_track_offset_m, 0.0)

    def test_nadir_centered_offset_zero(self):
        """Verify detection centered directly on nadir has 0.0 m across-track offset."""
        detections = [{"detection_id": "center", "bbox": {"x_min": 95.0, "y_min": 0.0, "width": 10.0, "height": 10.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=detections, navigation_track=self.track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertAlmostEqual(res.targets[0].georeference.across_track_offset_m, 0.0)


class TestPingTrackCorrelation(unittest.TestCase):
    """Unit tests validating correlation between detections and ping navigation telemetry."""

    def test_ping_index_matches_waterfall_row(self):
        """Verify target at waterfall row k correlates directly to track.points[k]."""
        pings = [
            SonarPingTelemetry(
                ping_index=i,
                timestamp=f"2026-09-18T12:00:{i:02d}Z",
                latitude=25.0 + i * 0.01,
                longitude=68.0 + i * 0.01,
                heading=0.0,
            )
            for i in range(5)
        ]
        track = SonarNavigationTrack(
            analysis_id="test_corr", source_format="XTF", total_pings=5, available_navigation_pings=5, points=pings
        )
        det = [{"detection_id": "d3", "bbox": {"x_min": 100.0, "y_min": 3.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        georef = res.targets[0].georeference
        self.assertEqual(georef.source_ping_index, 3)
        self.assertEqual(georef.waterfall_row, 3)
        self.assertAlmostEqual(georef.vessel_latitude, 25.03)
        self.assertAlmostEqual(georef.vessel_longitude, 68.03)

    def test_missing_navigation_yields_null_coords(self):
        """Verify ping with null GPS yields None coordinates and unavailable_missing_nav status."""
        pings = [
            SonarPingTelemetry(ping_index=0, timestamp="2026-09-18T12:00:00Z", latitude=24.0, longitude=67.0, heading=0.0),
            SonarPingTelemetry(ping_index=1, timestamp="2026-09-18T12:00:01Z", latitude=None, longitude=None, heading=0.0),
        ]
        track = SonarNavigationTrack(
            analysis_id="test_missing", source_format="XTF", total_pings=2, available_navigation_pings=1, points=pings
        )
        det = [{"detection_id": "d_unnav", "bbox": {"x_min": 110.0, "y_min": 1.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        target = res.targets[0]
        self.assertIsNone(target.coordinates)
        georef = target.georeference
        self.assertEqual(georef.status, "unavailable_missing_nav")
        self.assertIsNone(georef.latitude)
        self.assertIsNone(georef.longitude)
        self.assertIsNone(georef.vessel_latitude)
        self.assertIsNone(georef.vessel_longitude)
        self.assertTrue(any("missing" in w.lower() for w in georef.warnings))

    def test_no_zero_zero_coordinates_fabricated(self):
        """Verify missing navigation NEVER fabricates (0, 0) or default fallback."""
        pings = [SonarPingTelemetry(ping_index=0, timestamp="2026-09-18T12:00:00Z", latitude=None, longitude=None, heading=0.0)]
        track = SonarNavigationTrack(
            analysis_id="test_no_fabrication", source_format="JSF", total_pings=1, available_navigation_pings=0, points=pings
        )
        det = [{"detection_id": "d_zero", "bbox": {"x_min": 120.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertIsNone(res.targets[0].coordinates)
        self.assertIsNone(res.targets[0].georeference.latitude)
        self.assertIsNone(res.targets[0].georeference.longitude)
        # Ensure GeoJSON feature collection contains ZERO features
        self.assertEqual(len(res.geojson.features), 0)

    def test_missing_track_handled_gracefully(self):
        """Verify geolocate_sonar_detections handles navigation_track=None without crashing."""
        det = [{"detection_id": "d_notrack", "bbox": {"x_min": 110.0, "y_min": 5.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=None, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertEqual(len(res.targets), 1)
        self.assertEqual(res.targets[0].georeference.status, "unavailable_missing_nav")
        self.assertIsNone(res.targets[0].coordinates)

    def test_track_with_fewer_pings_than_detections(self):
        """Verify track with 2 pings receiving detections at row 5 clamps to ping 1."""
        pings = [
            SonarPingTelemetry(ping_index=0, timestamp="2026-09-18T12:00:00Z", latitude=24.1, longitude=67.1, heading=0.0),
            SonarPingTelemetry(ping_index=1, timestamp="2026-09-18T12:00:01Z", latitude=24.2, longitude=67.2, heading=0.0),
        ]
        track = SonarNavigationTrack(
            analysis_id="test_few", source_format="XTF", total_pings=2, available_navigation_pings=2, points=pings
        )
        det = [{"detection_id": "d_out", "bbox": {"x_min": 100.0, "y_min": 10.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertEqual(res.targets[0].georeference.source_ping_index, 1)
        self.assertAlmostEqual(res.targets[0].georeference.vessel_latitude, 24.2)


class TestGeospatialCalculation(unittest.TestCase):
    """Unit tests validating WGS84 projection physics, heading rotation, and layback."""

    def _make_single_ping_track(self, lat: float, lon: float, heading: float) -> SonarNavigationTrack:
        ping = SonarPingTelemetry(
            ping_index=0,
            timestamp="2026-09-18T12:00:00Z",
            latitude=lat,
            longitude=lon,
            heading=heading,
            altitude=15.0,
            depth=25.0,
        )
        return SonarNavigationTrack(
            analysis_id="test_geo",
            source_format="XTF",
            total_pings=1,
            available_navigation_pings=1,
            points=[ping],
        )

    def test_deterministic_wgs84_coordinates(self):
        """Verify calling georeference twice on identical inputs yields bit-identical WGS84 positions."""
        track = self._make_single_ping_track(lat=24.5000, lon=67.5000, heading=45.0)
        det = [{"detection_id": "det_det", "bbox": {"x_min": 130.0, "y_min": 0.0, "width": 10.0, "height": 10.0}}]
        res1 = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        res2 = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertEqual(res1.targets[0].coordinates.latitude, res2.targets[0].coordinates.latitude)
        self.assertEqual(res1.targets[0].coordinates.longitude, res2.targets[0].coordinates.longitude)

    def test_heading_0_starboard_shifts_east(self):
        """Heading 0 (North): Starboard (+across) must shift longitude East; latitude remains unchanged."""
        track = self._make_single_ping_track(lat=0.0, lon=0.0, heading=0.0)
        det = [{"detection_id": "sb_n", "bbox": {"x_min": 200.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        # nadir = 100, mpp = 1.0 -> offset = +100 m
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=1.0
        )
        coords = res.targets[0].coordinates
        self.assertAlmostEqual(coords.latitude, 0.0, places=6)
        self.assertGreater(coords.longitude, 0.0)

    def test_heading_90_starboard_shifts_south(self):
        """Heading 90 (East): Starboard (+across) must shift latitude South; longitude remains unchanged."""
        track = self._make_single_ping_track(lat=0.0, lon=0.0, heading=90.0)
        det = [{"detection_id": "sb_e", "bbox": {"x_min": 200.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=1.0
        )
        coords = res.targets[0].coordinates
        self.assertLess(coords.latitude, 0.0)
        self.assertAlmostEqual(coords.longitude, 0.0, places=6)

    def test_heading_180_starboard_shifts_west(self):
        """Heading 180 (South): Starboard (+across) must shift longitude West; latitude remains unchanged."""
        track = self._make_single_ping_track(lat=0.0, lon=0.0, heading=180.0)
        det = [{"detection_id": "sb_s", "bbox": {"x_min": 200.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=1.0
        )
        coords = res.targets[0].coordinates
        self.assertAlmostEqual(coords.latitude, 0.0, places=6)
        self.assertLess(coords.longitude, 0.0)

    def test_heading_270_starboard_shifts_north(self):
        """Heading 270 (West): Starboard (+across) must shift latitude North; longitude remains unchanged."""
        track = self._make_single_ping_track(lat=0.0, lon=0.0, heading=270.0)
        det = [{"detection_id": "sb_w", "bbox": {"x_min": 200.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=1.0
        )
        coords = res.targets[0].coordinates
        self.assertGreater(coords.latitude, 0.0)
        self.assertAlmostEqual(coords.longitude, 0.0, places=6)

    def test_towfish_layback_corrects_sensor_position(self):
        """Verify towfish layback calculates horizontal distance and places sensor astern of vessel."""
        # Heading 0 (North): Astern is South (decrease latitude)
        track = self._make_single_ping_track(lat=24.0, lon=67.0, heading=0.0)
        towfish = TowfishConfig(cable_payout_m=100.0, fish_depth_m=20.0)
        # Horizontal layback = sqrt(100^2 - 20^2) = sqrt(9600) ~ 97.98 m
        det = [{"detection_id": "d_lay", "bbox": {"x_min": 100.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det,
            navigation_track=track,
            nadir_pixel_x=100.0,
            meters_per_pixel=0.1,
            towfish_cfg=towfish,
        )
        georef = res.targets[0].georeference
        self.assertTrue(georef.layback_applied)
        expected_layback = np.sqrt(100**2 - 20**2) * towfish.catenary_factor
        self.assertAlmostEqual(georef.layback_distance_m, expected_layback, places=2)
        # Sensor should be South of vessel
        self.assertLess(georef.sensor_latitude, georef.vessel_latitude)
        self.assertAlmostEqual(georef.sensor_longitude, georef.vessel_longitude, places=6)

    def test_vessel_and_sensor_coords_distinct_with_layback(self):
        """Verify vessel coordinates and sensor coordinates are distinct when layback is applied."""
        track = self._make_single_ping_track(lat=25.0, lon=68.0, heading=45.0)
        towfish = TowfishConfig(cable_payout_m=50.0, fish_depth_m=10.0)
        det = [{"detection_id": "d_dist", "bbox": {"x_min": 120.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1, towfish_cfg=towfish
        )
        georef = res.targets[0].georeference
        self.assertNotEqual(georef.vessel_latitude, georef.sensor_latitude)
        self.assertNotEqual(georef.vessel_longitude, georef.sensor_longitude)

    def test_missing_meters_per_pixel_yields_null_coords(self):
        """Verify missing meters_per_pixel results in status='unavailable_missing_gsd' and null coordinates."""
        track = self._make_single_ping_track(lat=24.0, lon=67.0, heading=0.0)
        det = [{"detection_id": "d_nomsd", "bbox": {"x_min": 120.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=None
        )
        georef = res.targets[0].georeference
        self.assertEqual(georef.status, "unavailable_missing_gsd")
        self.assertIsNone(georef.latitude)
        self.assertIsNone(georef.longitude)
        self.assertIsNone(res.targets[0].coordinates)

    def test_coordinate_reference_always_wgs84(self):
        """Verify coordinate_reference is unconditionally 'WGS84'."""
        track = self._make_single_ping_track(lat=24.0, lon=67.0, heading=0.0)
        det = [{"detection_id": "d_ref", "bbox": {"x_min": 100.0, "y_min": 0.0, "width": 0.0, "height": 0.0}}]
        res = geolocation_service.geolocate_sonar_detections(
            detections=det, navigation_track=track, nadir_pixel_x=100.0, meters_per_pixel=0.1
        )
        self.assertEqual(res.targets[0].georeference.coordinate_reference, "WGS84")


class TestPipelineIntegration(unittest.TestCase):
    """End-to-end integration tests through MasterPipelineService for sonar and camera images."""

    def setUp(self):
        self.client = TestClient(app)

    @patch("app.services.master_pipeline_service.inference_service.predict_array")
    def test_sonar_detection_receives_georeference(self, mock_predict):
        """Sonar analysis with detections populates georeference on MasterTargetResult."""
        raw_dets = [
            {
                "detection_id": "det_sonar_01",
                "class_id": 1,
                "class_name": "container",
                "confidence": 0.92,
                "bbox": {"x_min": 80.0, "y_min": 2.0, "width": 20.0, "height": 2.0},
            }
        ]
        mock_predict.return_value = make_mock_detection_response(raw_dets, width=128, height=8)

        # Build synthetic XTF with 8 pings, nadir at x=64, lat=24.5, lon=67.5, heading=90
        coords = [(24.500 + i * 0.001, 67.500 + i * 0.001) for i in range(8)]
        xtf_bytes = build_custom_track_xtf(coords=coords, samples_per_chan=64, heading=90.0)

        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="georef_pipeline_test.xtf",
            max_pings=8,
        )

        self.assertEqual(len(result.targets), 1)
        target = result.targets[0]
        self.assertIsNotNone(target.georeference)
        self.assertEqual(target.georeference.status, "calculated")
        self.assertEqual(target.georeference.source_ping_index, 3)  # y_min=2, h=2 -> center_y=3
        self.assertIsNotNone(target.coordinates)
        self.assertIsNotNone(target.georeference.latitude)
        self.assertIsNotNone(target.georeference.longitude)
        self.assertEqual(target.georeference.coordinate_reference, "WGS84")

    @patch("app.services.master_pipeline_service.inference_service.predict_array")
    def test_multiple_detections_georeferenced_independently(self, mock_predict):
        """Multiple detections at different scanlines receive different source ping indices and coordinates."""
        raw_dets = [
            {
                "detection_id": "det_sonar_01",
                "class_id": 1,
                "class_name": "container",
                "confidence": 0.90,
                "bbox": {"x_min": 70.0, "y_min": 1.0, "width": 10.0, "height": 1.0},  # center_y = 1.5 -> row 2
            },
            {
                "detection_id": "det_sonar_02",
                "class_id": 2,
                "class_name": "pipe",
                "confidence": 0.85,
                "bbox": {"x_min": 50.0, "y_min": 5.0, "width": 10.0, "height": 1.0},  # center_y = 5.5 -> row 6
            },
        ]
        mock_predict.return_value = make_mock_detection_response(raw_dets, width=128, height=8)

        coords = [(24.500 + i * 0.005, 67.500 + i * 0.005) for i in range(8)]
        xtf_bytes = build_custom_track_xtf(coords=coords, samples_per_chan=64, heading=0.0)

        result = master_pipeline_service.execute_pipeline(
            image_bytes=xtf_bytes,
            filename="multi_det_test.xtf",
            max_pings=8,
        )

        self.assertEqual(len(result.targets), 2)
        t1, t2 = result.targets[0], result.targets[1]
        self.assertNotEqual(t1.georeference.source_ping_index, t2.georeference.source_ping_index)
        self.assertNotEqual(t1.coordinates.latitude, t2.coordinates.latitude)

    @patch("app.services.master_pipeline_service.inference_service.predict_array")
    def test_camera_image_unaffected_by_sonar_georef(self, mock_predict):
        """Conventional camera image upload preserves standard projection and has georeference=None."""
        raw_dets = [
            {
                "detection_id": "det_opt_01",
                "class_id": 1,
                "class_name": "debris",
                "confidence": 0.88,
                "bbox": {"x_min": 20.0, "y_min": 20.0, "width": 30.0, "height": 30.0},
            }
        ]
        mock_predict.return_value = make_mock_detection_response(raw_dets, width=100, height=100)

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, enc = cv2.imencode(".jpg", img)
        jpg_bytes = enc.tobytes()

        result = master_pipeline_service.execute_pipeline(
            image_bytes=jpg_bytes,
            filename="optical_survey.jpg",
            vessel_lat=24.8607,
            vessel_lon=67.0011,
            vessel_heading_deg=45.0,
        )

        self.assertEqual(len(result.targets), 1)
        target = result.targets[0]
        # Camera image target: georeference is None
        self.assertIsNone(target.georeference)
        # Standard coordinates are calculated from vessel fix
        self.assertIsNotNone(target.coordinates)
        self.assertAlmostEqual(target.coordinates.latitude, 24.8607, places=3)
        self.assertAlmostEqual(target.coordinates.longitude, 67.0011, places=3)

    @patch("app.services.master_pipeline_service.inference_service.predict_array")
    def test_sonar_metadata_track_artifact_associated(self, mock_predict):
        """Analysis response contains sonar_metadata with valid track_artifact_id and track_reference."""
        mock_predict.return_value = make_mock_detection_response([], width=128, height=8)
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64)
        result = master_pipeline_service.execute_pipeline(image_bytes=xtf_bytes, filename="artifact_assoc.xtf", max_pings=8)

        self.assertIsNotNone(result.sonar_metadata)
        self.assertIsNotNone(result.sonar_metadata.track_artifact_id)
        self.assertIsNotNone(result.sonar_metadata.track_reference)


class TestHydrographicExports(unittest.TestCase):
    """Tests validating hydrographic exports incorporate georeference data cleanly."""

    def setUp(self):
        self.synthetic_georef = SonarTargetGeoreference(
            status="calculated",
            coordinate_reference="WGS84",
            latitude=24.86075,
            longitude=67.00115,
            source_ping_index=4,
            waterfall_row=4,
            across_track_pixel=120.0,
            across_track_offset_m=5.25,
            slant_range_m=50.0,
            heading_deg=90.0,
            layback_applied=True,
            layback_distance_m=48.99,
            vessel_latitude=24.86070,
            vessel_longitude=67.00110,
            sensor_latitude=24.86072,
            sensor_longitude=67.00112,
        )
        self.synthetic_result = {
            "mission_id": "msn_export_test",
            "status": "success",
            "sonar_metadata": {
                "format": "XTF",
                "waterfall_width": 256,
                "waterfall_height": 10,
                "total_pings": 10,
                "navigation": {
                    "latitude": 24.8607,
                    "longitude": 67.0011,
                    "heading": 90.0,
                },
            },
            "targets": [
                {
                    "detection_id": "det_with_geo",
                    "class_name": "container",
                    "display_name": "Shipping Container",
                    "category": "Cargo Debris",
                    "calibrated_confidence": 0.94,
                    "ai_confidence": 0.95,
                    "trust_tier": "VERIFIED_DEBRIS",
                    "bbox": {"x_min": 110.0, "y_min": 3.0, "width": 20.0, "height": 2.0},
                    "coordinates": {
                        "latitude": 24.86075,
                        "longitude": 67.00115,
                        "dms_string": "24°51'38.7\"N 67°00'04.1\"E",
                        "utm_zone": "42N",
                        "utm_easting_m": 300000.0,
                        "utm_northing_m": 2750000.0,
                    },
                    "distance_from_sensor_m": 5.25,
                    "bearing_degrees": 180.0,
                    "dimensions": {"length_m": 12.0, "width_m": 2.4, "height_m": 2.6, "area_sq_m": 28.8},
                    "risk_score": 85.0,
                    "risk_tier": "CRITICAL",
                    "clearance": {"clearance_m": 3.5, "water_depth_m": 20.0},
                    "action_recommendations": [{"action_text": "Immediate NOTMAR required"}],
                    "georeference": self.synthetic_georef.model_dump(),
                },
                {
                    "detection_id": "det_without_geo",
                    "class_name": "trawl_gear",
                    "display_name": "Ghost Net / Trawl Gear",
                    "category": "Fishing Debris",
                    "calibrated_confidence": 0.70,
                    "ai_confidence": 0.72,
                    "trust_tier": "PROBABLE_DEBRIS",
                    "bbox": {"x_min": 50.0, "y_min": 8.0, "width": 10.0, "height": 2.0},
                    "coordinates": None,
                    "distance_from_sensor_m": None,
                    "bearing_degrees": None,
                    "dimensions": {"length_m": 5.0, "width_m": 2.0, "height_m": 1.0, "area_sq_m": 10.0},
                    "risk_score": 45.0,
                    "risk_tier": "MODERATE",
                    "clearance": {"clearance_m": 15.0, "water_depth_m": 20.0},
                    "action_recommendations": [],
                    "georeference": {
                        "status": "unavailable_missing_nav",
                        "coordinate_reference": "WGS84",
                        "latitude": None,
                        "longitude": None,
                        "source_ping_index": 9,
                        "waterfall_row": 9,
                        "across_track_pixel": 55.0,
                        "across_track_offset_m": -4.5,
                        "layback_applied": False,
                        "warnings": ["Ping navigation telemetry missing"],
                    },
                },
            ],
        }

    def test_geojson_target_features_have_lon_lat(self):
        """Verify RFC 7946 strictly requires [longitude, latitude] coordinate ordering."""
        geojson = hydrographic_export_service.export_geojson(self.synthetic_result)
        self.assertEqual(len(geojson["features"]), 1)
        feat = geojson["features"][0]
        coords = feat["geometry"]["coordinates"]
        # Expected: [longitude, latitude]
        self.assertAlmostEqual(coords[0], 67.00115)
        self.assertAlmostEqual(coords[1], 24.86075)

    def test_geojson_omits_targets_without_coords(self):
        """Verify detection with null coordinates is completely omitted from GeoJSON features."""
        geojson = hydrographic_export_service.export_geojson(self.synthetic_result)
        feature_ids = [f["properties"]["detection_id"] for f in geojson["features"]]
        self.assertIn("det_with_geo", feature_ids)
        self.assertNotIn("det_without_geo", feature_ids)

    def test_geojson_feature_properties_include_georef(self):
        """Verify feature properties include georeference and ping metadata."""
        geojson = hydrographic_export_service.export_geojson(self.synthetic_result)
        props = geojson["features"][0]["properties"]
        self.assertIn("georeference", props)
        self.assertEqual(props["source_ping_index"], 4)
        self.assertEqual(props["waterfall_row"], 4)
        self.assertAlmostEqual(props["across_track_offset_m"], 5.25)
        self.assertTrue(props["layback_applied"])

    def test_csv_export_includes_georef_columns(self):
        """Verify CSV header contains georeference columns and detection row populates them."""
        csv_text = hydrographic_export_service.export_csv(self.synthetic_result)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        self.assertEqual(len(rows), 2)

        # Check headers
        self.assertIn("source_ping_index", reader.fieldnames)
        self.assertIn("waterfall_row", reader.fieldnames)
        self.assertIn("across_track_offset_m", reader.fieldnames)
        self.assertIn("layback_applied", reader.fieldnames)

        # Check row 1 (with geo)
        r1 = rows[0]
        self.assertEqual(r1["detection_id"], "det_with_geo")
        self.assertEqual(r1["source_ping_index"], "4")
        self.assertEqual(r1["waterfall_row"], "4")
        self.assertEqual(r1["across_track_offset_m"], "5.25")
        self.assertEqual(r1["layback_applied"], "True")

    def test_csv_export_handles_null_coords(self):
        """Verify detection without coordinates writes empty string for lat/lon, never 0.0."""
        csv_text = hydrographic_export_service.export_csv(self.synthetic_result)
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        r2 = rows[1]
        self.assertEqual(r2["detection_id"], "det_without_geo")
        self.assertEqual(r2["latitude"], "")
        self.assertEqual(r2["longitude"], "")
        self.assertNotEqual(r2["latitude"], "0.0")

    def test_json_export_backward_compatible(self):
        """Verify export_json preserves complete schema and includes georeference."""
        json_pkg = hydrographic_export_service.export_json(self.synthetic_result)
        self.assertEqual(json_pkg["schema_version"], "1.0")
        self.assertEqual(len(json_pkg["detections"]), 2)
        d1 = json_pkg["detections"][0]
        self.assertIn("georeference", d1)
        self.assertEqual(d1["georeference"]["status"], "calculated")
        self.assertEqual(d1["georeference"]["source_ping_index"], 4)


class TestRegressionEndpoints(unittest.TestCase):
    """Regression tests verifying existing Phase 6B, 7, and 8 endpoints remain fully operational."""

    def setUp(self):
        self.client = TestClient(app)

    def test_raster_retrieval_still_works(self):
        """Verify GET /api/v1/analyses/{id}/sonar/raster returns 200 image/png."""
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("regress_raster.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        raster_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/raster")
        self.assertEqual(raster_resp.status_code, 200)
        self.assertEqual(raster_resp.headers["content-type"], "image/png")

    def test_track_endpoint_still_works(self):
        """Verify GET /api/v1/analyses/{id}/sonar/track returns 200 SonarNavigationTrack."""
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("regress_track.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        track_resp = self.client.get(f"/api/v1/analyses/{analysis_id}/sonar/track")
        self.assertEqual(track_resp.status_code, 200)
        data = track_resp.json()
        self.assertEqual(data["analysis_id"], analysis_id)
        self.assertEqual(data["total_pings"], 8)

    def test_export_endpoints_still_work(self):
        """Verify /export/json, /export/csv, /export/geojson, /export/track.geojson, /export/track.csv all return 200."""
        xtf_bytes = build_synthetic_xtf_binary(num_pings=8, samples_per_chan=64)
        post_resp = self.client.post(
            "/api/v1/analyses/sonar",
            files={"file": ("regress_exports.xtf", io.BytesIO(xtf_bytes), "application/octet-stream")},
        )
        self.assertEqual(post_resp.status_code, 200)
        analysis_id = post_resp.json()["mission_id"]

        for ep, expected_ct in [
            (f"/api/v1/analyses/{analysis_id}/export/json", "application/json"),
            (f"/api/v1/analyses/{analysis_id}/export/csv", "text/csv"),
            (f"/api/v1/analyses/{analysis_id}/export/geojson", "application/geo+json"),
            (f"/api/v1/analyses/{analysis_id}/export/track.geojson", "application/geo+json"),
            (f"/api/v1/analyses/{analysis_id}/export/track.csv", "text/csv"),
        ]:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, 200, f"Endpoint {ep} failed with {resp.status_code}")
            self.assertIn(expected_ct, resp.headers["content-type"])


if __name__ == "__main__":
    unittest.main()
