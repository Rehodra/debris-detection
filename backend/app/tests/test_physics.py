"""
Unit and integration tests for MarineScan Physics Service.
Tests ocean acoustics, Mackenzie sound speed, slant-to-ground range geometry,
3D volumetric and mass estimation, buoyancy, hydrodynamic stability,
and full synthesis with AI detections and shadow evidence.
"""

import unittest
import numpy as np
import cv2
from fastapi.testclient import TestClient

try:
    from app.main import app
    from app.core.config import settings
    from app.services.physics_service import physics_service
    from app.schemas.physics import (
        OceanEnvironmentParams,
        SedimentType,
    )
    from app.schemas.shadow import ShadowAnalysisResult, ShadowExtent
except ImportError:
    from backend.app.main import app
    from backend.app.core.config import settings
    from backend.app.services.physics_service import physics_service
    from backend.app.schemas.physics import (
        OceanEnvironmentParams,
        SedimentType,
    )
    from backend.app.schemas.shadow import ShadowAnalysisResult, ShadowExtent


class TestPhysicsService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_context = TestClient(app)
        cls.client = cls._client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_context.__exit__(None, None, None)

    def _create_sample_jpeg_bytes(self) -> bytes:
        img = np.full((400, 400, 3), 70, dtype=np.uint8)
        # Target
        cv2.rectangle(img, (120, 150), (200, 220), (220, 220, 220), -1)
        # Shadow
        cv2.rectangle(img, (200, 150), (280, 220), (10, 10, 10), -1)
        _, buf = cv2.imencode(".jpg", img)
        return buf.tobytes()

    def test_sound_speed_mackenzie(self):
        # Benchmark: T = 12 C, S = 35 ppt, D = 30 m -> ~1497 m/s
        speed = physics_service.calculate_sound_speed(temperature_c=12.0, salinity_ppt=35.0, depth_m=30.0)
        self.assertAlmostEqual(speed, 1497.31, delta=0.5)

        # Deeper water increases sound speed due to hydrostatic pressure
        deep_speed = physics_service.calculate_sound_speed(temperature_c=12.0, salinity_ppt=35.0, depth_m=1000.0)
        self.assertGreater(deep_speed, speed)

    def test_sonar_geometry_slant_to_ground(self):
        # 3-4-5 triangle: Altitude = 30m, Ground Range = 40m -> Slant Range = 50m
        geom = physics_service.calculate_sonar_geometry(sensor_altitude_m=30.0, slant_range_m=50.0)
        self.assertEqual(geom.sensor_altitude_m, 30.0)
        self.assertEqual(geom.slant_range_m, 50.0)
        self.assertAlmostEqual(geom.ground_range_m, 40.0, delta=0.01)
        # sin(grazing) = 30/50 = 0.6 -> arcsin(0.6) = 36.87 deg
        self.assertAlmostEqual(geom.grazing_angle_degrees, 36.87, delta=0.1)

    def test_estimate_3d_properties_shipwreck(self):
        # 20m length, 5m width, modeled height = min(20, 5) * 0.45 = 2.25m
        props = physics_service.estimate_3d_properties("shipwreck", length_m=20.0, width_m=5.0)
        self.assertEqual(props.height_source, "aspect_modeled")
        self.assertEqual(props.height_m, 2.25)
        # Volume = 20 * 5 * 2.25 * 0.65 = 146.25 m^3
        self.assertAlmostEqual(props.estimated_volume_m3, 146.25, delta=0.1)
        # Dry mass = 146.25 * 1800 kg/m^3 / 1000 = 263.25 tons
        self.assertAlmostEqual(props.dry_mass_metric_tons, 263.25, delta=0.1)
        # Buoyant force = 1025 * 146.25 * 9.80665 / 1000 = 1470.08 kN
        self.assertGreater(props.buoyant_force_kn, 1400.0)
        # Submerged weight = dry weight - buoyant force > 0
        self.assertGreater(props.submerged_weight_kn, 0.0)
        # Crane lift rating should include 1.5x safety factor
        self.assertAlmostEqual(props.recommended_crane_lift_tons, props.submerged_mass_metric_tons * 1.5, delta=0.2)

    def test_estimate_3d_properties_with_shadow_evidence(self):
        # Shadow indicates a 3.8m tall vertical relief
        props = physics_service.estimate_3d_properties(
            "aircraft",
            length_m=15.0,
            width_m=12.0,
            shadow_height_m=3.8,
        )
        self.assertEqual(props.height_source, "shadow_derived")
        self.assertEqual(props.height_m, 3.8)
        # Volume = 15 * 12 * 3.8 * 0.35 = 239.4 m^3
        self.assertAlmostEqual(props.estimated_volume_m3, 239.4, delta=0.5)

    def test_hydrodynamic_stability_stable_vs_unstable(self):
        # Heavy submerged shipwreck on sand
        stable = physics_service.assess_hydrodynamic_stability(
            class_name="shipwreck",
            width_m=6.0,
            height_m=3.0,
            submerged_weight_kn=1500.0,
            bottom_current_mps=0.8,
            sediment_type=SedimentType.FINE_SAND,
        )
        self.assertEqual(stable.mobility_status, "Settled / Stable in Sediment")
        self.assertGreater(stable.stability_index, 1.5)

        # Light debris under high current
        unstable = physics_service.assess_hydrodynamic_stability(
            class_name="other",
            width_m=4.0,
            height_m=3.0,
            submerged_weight_kn=5.0,  # Very light
            bottom_current_mps=2.5,   # Strong 2.5 m/s current
            sediment_type=SedimentType.MUD_SILT,
        )
        self.assertEqual(unstable.mobility_status, "Unstable / Migrating Debris Hazard")
        self.assertLess(unstable.stability_index, 1.0)

    def test_physical_plausibility(self):
        # Realistic shipwreck
        plausible = physics_service.verify_physical_plausibility(
            "shipwreck", length_m=35.0, width_m=8.0, height_m=5.0, has_shadow_evidence=True
        )
        self.assertTrue(plausible.is_plausible)
        self.assertGreaterEqual(plausible.physical_validation_score, 0.8)

        # Impossible aircraft (300m length is larger than an aircraft carrier)
        implausible = physics_service.verify_physical_plausibility(
            "aircraft", length_m=300.0, width_m=40.0, height_m=10.0
        )
        self.assertFalse(implausible.is_plausible)
        self.assertLess(implausible.physical_validation_score, 0.7)

    def test_api_environment_endpoint(self):
        response = self.client.get(
            f"{settings.API_V1_STR}/physics/environment?temperature_c=14.0&salinity_ppt=34.5&depth_m=45.0"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("sound_speed_mps", data)
        self.assertIn("absorption_db_per_km", data)
        self.assertIn("acoustic_wavelength_mm", data)
        self.assertGreater(data["sound_speed_mps"], 1450.0)

    def test_api_analyze_target_endpoint(self):
        response = self.client.post(
            f"{settings.API_V1_STR}/physics/analyze-target?class_name=shipwreck&length_m=28.0&width_m=6.5&sensor_altitude_m=15.0&slant_range_m=45.0"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["class_name"], "shipwreck")
        self.assertIn("physical_properties", data)
        self.assertIn("hydrodynamic_stability", data)
        self.assertIn("plausibility", data)
        self.assertIn("sonar_geometry", data)
        self.assertIsNotNone(data["sonar_geometry"])

    def test_api_analyze_image_endpoint(self):
        jpeg_bytes = self._create_sample_jpeg_bytes()
        files = {"file": ("test_sonar.jpg", jpeg_bytes, "image/jpeg")}
        response = self.client.post(
            f"{settings.API_V1_STR}/physics/analyze-image?confidence_threshold=0.10&sensor_altitude_m=12.0&slant_range_m=35.0",
            files=files,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("total_targets_analyzed", data)
        self.assertIn("results", data)


if __name__ == "__main__":
    unittest.main()
