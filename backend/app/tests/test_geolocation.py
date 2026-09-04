"""
Unit and integration tests for MarineScan Geolocation Service.
Tests WGS84 ellipsoidal geodesy, towfish catenary layback,
navigational azimuth heading rotation, UTM / DMS conversions,
standard GeoJSON FeatureCollection generation, and API endpoints.
"""

import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.services.geolocation_service import geolocation_service
    from app.schemas.geolocation import (
        NavigationalFix,
        TowfishConfig,
        SonarScanOrigin,
    )
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.services.geolocation_service import geolocation_service
    from backend.app.schemas.geolocation import (
        NavigationalFix,
        TowfishConfig,
        SonarScanOrigin,
    )


class TestGeolocationService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self) -> bytes:
        img = np.full((400, 400, 3), 70, dtype=np.uint8)
        cv2.rectangle(img, (150, 150), (220, 220), (220, 220, 220), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def test_wgs84_direct_projection(self):
        # 1 degree of latitude is roughly 111 km (110,852m at lat 24)
        origin_lat, origin_lon = 24.8607, 67.0011
        target_lat, target_lon = geolocation_service.wgs84_direct_projection(
            lat_deg=origin_lat,
            lon_deg=origin_lon,
            delta_east_m=0.0,
            delta_north_m=110852.0,
        )
        self.assertAlmostEqual(target_lat, origin_lat + 1.0, delta=0.01)
        self.assertEqual(target_lon, origin_lon)

    def test_towfish_layback_calculation(self):
        # Vessel heading North (0 deg)
        vessel = NavigationalFix(latitude=25.0, longitude=65.0, heading_degrees=0.0)
        # 100m cable, 20m depth: straight layback = sqrt(10000 - 400) = 97.98m
        # With catenary factor 0.95: layback = 93.08m
        fish_coords, layback = geolocation_service.calculate_towfish_position(
            vessel_fix=vessel,
            towfish_cfg=TowfishConfig(cable_payout_m=100.0, fish_depth_m=20.0, catenary_factor=0.95),
        )
        self.assertAlmostEqual(layback, 93.08, delta=0.1)
        # Towfish should be directly SOUTH of the vessel (lower latitude)
        self.assertLess(fish_coords.latitude, vessel.latitude)
        self.assertEqual(fish_coords.longitude, vessel.longitude)

    def test_pixel_to_track_offsets(self):
        origin = SonarScanOrigin(
            nadir_pixel_x=500.0,
            reference_pixel_y=100.0,
            across_track_gsd_m=0.1,
            along_track_gsd_m=0.1,
        )
        # Starboard pixel (x=700 > 500)
        across_stbd, along_stbd = geolocation_service.pixel_to_seafloor_offset(700.0, 100.0, origin)
        self.assertEqual(across_stbd, 20.0)  # +20m starboard
        self.assertEqual(along_stbd, 0.0)

        # Port pixel (x=300 < 500)
        across_port, along_port = geolocation_service.pixel_to_seafloor_offset(300.0, 150.0, origin)
        self.assertEqual(across_port, -20.0)  # -20m port
        self.assertEqual(along_port, 5.0)     # +5m forward

    def test_heading_rotations_cardinal(self):
        origin = SonarScanOrigin(nadir_pixel_x=500.0, across_track_gsd_m=1.0, along_track_gsd_m=1.0)

        # Case 1: Heading North (0 deg), target is 50m starboard (East)
        vessel_n = NavigationalFix(latitude=20.0, longitude=60.0, heading_degrees=0.0)
        target_n = geolocation_service.geolocate_target("t1", "shipwreck", 0.9, 550.0, 0.0, vessel_n, origin)
        self.assertAlmostEqual(target_n.bearing_degrees, 90.0, delta=0.5)  # East
        self.assertEqual(target_n.distance_from_sensor_m, 50.0)

        # Case 2: Heading East (90 deg), target is 50m starboard (South)
        vessel_e = NavigationalFix(latitude=20.0, longitude=60.0, heading_degrees=90.0)
        target_e = geolocation_service.geolocate_target("t2", "shipwreck", 0.9, 550.0, 0.0, vessel_e, origin)
        self.assertAlmostEqual(target_e.bearing_degrees, 180.0, delta=0.5)  # South

        # Case 3: Heading South (180 deg), target is 50m starboard (West)
        vessel_s = NavigationalFix(latitude=20.0, longitude=60.0, heading_degrees=180.0)
        target_s = geolocation_service.geolocate_target("t3", "shipwreck", 0.9, 550.0, 0.0, vessel_s, origin)
        self.assertAlmostEqual(target_s.bearing_degrees, 270.0, delta=0.5)  # West

    def test_dms_and_utm_formatting(self):
        # Coordinates for Boston Harbor ~ 42.36 N, 71.05 W
        coords = geolocation_service.to_geo_coordinates(42.3601, -71.0589)
        self.assertIn("N", coords.dms_string)
        self.assertIn("W", coords.dms_string)
        self.assertEqual(coords.utm_zone, "19N")
        self.assertGreater(coords.utm_easting_m, 300000.0)
        self.assertGreater(coords.utm_northing_m, 4000000.0)

    def test_batch_geojson_generation(self):
        vessel = NavigationalFix(latitude=24.0, longitude=67.0, heading_degrees=45.0)
        origin = SonarScanOrigin(nadir_pixel_x=320.0, across_track_gsd_m=0.05, along_track_gsd_m=0.05)
        detections = [
            {
                "detection_id": "det_1",
                "class_name": "shipwreck",
                "confidence": 0.91,
                "bbox": {"x_min": 400.0, "y_min": 50.0, "width": 40.0, "height": 30.0},
            }
        ]

        batch_resp = geolocation_service.geolocate_batch(detections, vessel, origin)
        self.assertEqual(batch_resp.total_targets_geolocated, 1)
        self.assertEqual(batch_resp.geojson.type, "FeatureCollection")
        self.assertEqual(len(batch_resp.geojson.features), 1)

        feature = batch_resp.geojson.features[0]
        self.assertEqual(feature.type, "Feature")
        self.assertEqual(feature.geometry.type, "Point")
        # GeoJSON order: [longitude, latitude]
        self.assertEqual(len(feature.geometry.coordinates), 2)
        self.assertEqual(feature.properties["class_name"], "shipwreck")

    def test_api_layback_endpoint(self):
        response = self.client.post(
            f"{settings.API_V1_STR}/geolocation/layback?vessel_lat=24.5&vessel_lon=68.0&vessel_heading_deg=180.0&cable_payout_m=80.0&fish_depth_m=15.0"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("latitude", data)
        self.assertIn("longitude", data)
        self.assertIn("dms_string", data)
        self.assertIn("utm_zone", data)

    def test_api_target_endpoint(self):
        response = self.client.post(
            f"{settings.API_V1_STR}/geolocation/target?pixel_x=600&pixel_y=100&sensor_lat=25.0&sensor_lon=66.0&sensor_heading_deg=0.0&nadir_pixel_x=500"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["class_name"], "shipwreck")
        self.assertIn("coordinates", data)
        self.assertIn("distance_from_sensor_m", data)
        self.assertIn("bearing_degrees", data)

    def test_api_analyze_image_endpoint(self):
        jpeg_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/geolocation/analyze-image?vessel_lat=24.8&vessel_lon=67.1&vessel_heading_deg=45.0&confidence_threshold=0.10",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_targets_geolocated", data)
        self.assertIn("sensor_position", data)
        self.assertIn("geojson", data)
        self.assertEqual(data["geojson"]["type"], "FeatureCollection")


if __name__ == "__main__":
    unittest.main()
