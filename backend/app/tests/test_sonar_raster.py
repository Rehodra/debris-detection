"""
Unit Tests for MarineScan Normalized Acoustic Waterfall Raster Layer.

Phase 2B Verification Suite.
Tests:
  1. Empty input handling
  2. Single ping assembly
  3. Multiple pings along-track assembly
  4. Varying sample lengths & nadir column alignment
  5. Port-only channel selection & orientation
  6. Starboard-only channel selection & orientation
  7. Dual-channel assembly & horizontal coordinate system
  8. Missing channel handling & safe padding
  9. max_pings memory bounding
 10. NaN / Inf / Negative acoustic sample sanitization
 11. Deterministic percentile intensity normalization
 12. Correct raster dimensions & metadata contracts
 13. Correct nadir placement (symmetric, asymmetric, single-channel)
 14. Invalid channel selection validation (negative IDs, empty list, non-existent)
 15. Real physical units preservation (no fabrication of resolution/slant range)
 16. Integration with XtfSonarParser.build_waterfall_raster using synthetic buffers

Note:
  Tests use verified in-memory acoustic NumPy buffers and synthetic XTF structures.
  They do NOT claim to be real-world recorded XTF files.
"""

import io
import unittest
from typing import Dict, List, Optional

import numpy as np

from app.sonar.raster_reader import SonarRasterBuilder
from app.sonar.xtf_reader import XtfSonarParser
from app.tests.test_xtf_parser import build_synthetic_xtf_binary


class TestSonarRasterBuilder(unittest.TestCase):
    """
    Test suite for pure-logic SonarRasterBuilder.
    """

    def setUp(self):
        # Deterministic seed for reproducible tests
        np.random.seed(42)

    def test_01_empty_input(self):
        """
        Empty ping input must return shape (0, 0) uint8 raster with explicit warning.
        No fabricated coordinates or resolutions.
        """
        raster, meta = SonarRasterBuilder.assemble_scanlines([])

        self.assertIsInstance(raster, np.ndarray)
        self.assertEqual(raster.shape, (0, 0))
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(meta["total_pings"], 0)
        self.assertEqual(meta["sample_width"], 0)
        self.assertIsNone(meta["nadir_pixel_x"])
        self.assertIsNone(meta["meters_per_pixel"])
        self.assertIsNone(meta["slant_range_m"])
        self.assertEqual(meta["channel_layout"], "empty")
        self.assertTrue(any("No acoustic pings provided" in w for w in meta["warnings"]))

    def test_02_one_ping(self):
        """
        Single ping with dual channels (50 port, 50 starboard) must assemble into (1, 100) uint8.
        """
        port = np.linspace(10.0, 100.0, 50, dtype=np.float32)
        stbd = np.linspace(10.0, 100.0, 50, dtype=np.float32)
        pings = [{0: port, 1: stbd}]

        raster, meta = SonarRasterBuilder.assemble_scanlines(pings)

        self.assertEqual(raster.shape, (1, 100))
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(meta["total_pings"], 1)
        self.assertEqual(meta["sample_width"], 100)
        self.assertEqual(meta["nadir_pixel_x"], 50.0)
        self.assertEqual(meta["channel_layout"], "port_nadir_starboard")
        self.assertGreaterEqual(raster.min(), 0)
        self.assertLessEqual(raster.max(), 255)

    def test_03_multiple_pings(self):
        """
        Sequence of 10 pings along-track must produce (10, W) raster.
        """
        num_pings = 10
        samples_per_chan = 64
        pings = [
            {
                0: np.random.uniform(5.0, 80.0, samples_per_chan).astype(np.float32),
                1: np.random.uniform(5.0, 80.0, samples_per_chan).astype(np.float32),
            }
            for _ in range(num_pings)
        ]

        raster, meta = SonarRasterBuilder.assemble_scanlines(pings)

        self.assertEqual(raster.shape, (10, 128))
        self.assertEqual(meta["total_pings"], 10)
        self.assertEqual(meta["sample_width"], 128)
        self.assertEqual(meta["nadir_pixel_x"], 64.0)

    def test_04_varying_sample_lengths(self):
        """
        Safely align pings with different sample counts without corrupting nadir alignment.
        Port is right-aligned against nadir (far-range padded at left).
        Starboard is left-aligned against nadir (far-range padded at right).
        """
        # Ping 0: 100 port, 100 stbd
        # Ping 1: 70 port, 80 stbd
        # Ping 2: 90 port, 60 stbd
        ping0 = {0: np.full(100, 40.0, dtype=np.float32), 1: np.full(100, 40.0, dtype=np.float32)}
        # Give ping 1 distinctive near-nadir markers: port sample 0 is 99.0, stbd sample 0 is 88.0
        p1_port = np.full(70, 30.0, dtype=np.float32)
        p1_port[0] = 99.0  # near-nadir sample
        p1_stbd = np.full(80, 30.0, dtype=np.float32)
        p1_stbd[0] = 88.0  # near-nadir sample
        ping1 = {0: p1_port, 1: p1_stbd}
        ping2 = {0: np.full(90, 50.0, dtype=np.float32), 1: np.full(60, 50.0, dtype=np.float32)}

        pings = [ping0, ping1, ping2]
        raster, meta = SonarRasterBuilder.assemble_scanlines(pings)

        max_port = 100
        max_stbd = 100
        total_width = max_port + max_stbd
        self.assertEqual(raster.shape, (3, total_width))
        self.assertEqual(meta["sample_width"], 200)
        self.assertEqual(meta["nadir_pixel_x"], 100.0)

        # For Ping 1 (row 1):
        # Port was 70 samples, so columns [0 : 30] must be zero-padded far range.
        self.assertTrue(np.all(raster[1, 0:30] == 0))
        # Port is reversed, so sample 0 (near nadir) should be at column max_port - 1 = 99.
        # Check that column 99 has high intensity (corresponding to our 99.0 marker).
        self.assertGreater(raster[1, 99], raster[1, 29])

        # Starboard was 80 samples, placed in columns [100 : 180].
        # Starboard sample 0 is at column 100 (adjacent to nadir line at 100).
        self.assertGreater(raster[1, 100], 0)
        # Columns [180 : 200] must be zero-padded far range.
        self.assertTrue(np.all(raster[1, 180:200] == 0))

        # Warnings should record length variations
        self.assertTrue(any("shorter than max" in w for w in meta["warnings"]))

    def test_05_port_only(self):
        """
        Port-only request ([0]) must produce (H, max_port_len) raster with nadir at right edge.
        Port samples must be reversed horizontally.
        """
        # Port sample 0 = 10.0 (near nadir), sample 49 = 90.0 (far range)
        port = np.linspace(10.0, 90.0, 50, dtype=np.float32)
        stbd = np.linspace(100.0, 200.0, 50, dtype=np.float32)
        pings = [{0: port, 1: stbd}]

        raster, meta = SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[0])

        self.assertEqual(raster.shape, (1, 50))
        self.assertEqual(meta["channel_layout"], "port_only")
        self.assertEqual(meta["channels_included"], [0])
        self.assertEqual(meta["nadir_pixel_x"], 50.0)  # rightmost boundary

        # Because port is reversed:
        # Col 0 (left) is far-range (orig sample 49, value 90.0)
        # Col 49 (right) is near-nadir (orig sample 0, value 10.0)
        self.assertGreater(raster[0, 0], raster[0, 49])

    def test_06_starboard_only(self):
        """
        Starboard-only request ([1]) must produce (H, max_stbd_len) raster with nadir at left edge (0.0).
        Starboard samples must NOT be reversed.
        """
        port = np.linspace(10.0, 90.0, 50, dtype=np.float32)
        # Starboard sample 0 = 10.0 (near nadir), sample 49 = 90.0 (far range)
        stbd = np.linspace(10.0, 90.0, 50, dtype=np.float32)
        pings = [{0: port, 1: stbd}]

        raster, meta = SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[1])

        self.assertEqual(raster.shape, (1, 50))
        self.assertEqual(meta["channel_layout"], "starboard_only")
        self.assertEqual(meta["channels_included"], [1])
        self.assertEqual(meta["nadir_pixel_x"], 0.0)  # leftmost boundary

        # Because starboard is unreversed:
        # Col 0 (left) is near-nadir (orig sample 0, value 10.0)
        # Col 49 (right) is far-range (orig sample 49, value 90.0)
        self.assertLess(raster[0, 0], raster[0, 49])

    def test_07_dual_channel(self):
        """
        Dual-channel layout must place Port on left (reversed) and Starboard on right (unreversed).
        Nadir line is at column max_port_len.
        """
        port = np.arange(1, 51, dtype=np.float32)  # sample 0 is 1.0 (near nadir), sample 49 is 50.0 (far)
        stbd = np.arange(101, 151, dtype=np.float32)  # sample 0 is 101.0 (near nadir), sample 49 is 150.0 (far)
        pings = [{0: port, 1: stbd}]

        raster, meta = SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[0, 1])

        self.assertEqual(raster.shape, (1, 100))
        self.assertEqual(meta["channel_layout"], "port_nadir_starboard")
        self.assertEqual(meta["nadir_pixel_x"], 50.0)

        # Port is columns [0..49].
        # Col 0 is far port (orig sample 49)
        # Col 49 is near-nadir port (orig sample 0)
        # Starboard is columns [50..99].
        # Col 50 is near-nadir starboard (orig sample 0)
        # Col 99 is far starboard (orig sample 49)
        # Verify orientation:
        self.assertGreater(raster[0, 0], raster[0, 49])  # Far port (50) > near-nadir port (1)
        self.assertLess(raster[0, 50], raster[0, 99])    # Near-nadir stbd (101) < far stbd (150)

    def test_08_missing_channel(self):
        """
        Handle pings where individual channels are missing or omitted.
        Missing channels must be safely zero-padded without crashing.
        """
        ping0 = {0: np.ones(50, dtype=np.float32) * 50.0, 1: np.ones(50, dtype=np.float32) * 50.0}
        ping1 = {0: np.ones(50, dtype=np.float32) * 50.0}  # missing Starboard
        ping2 = {1: np.ones(50, dtype=np.float32) * 50.0}  # missing Port

        raster, meta = SonarRasterBuilder.assemble_scanlines([ping0, ping1, ping2])

        self.assertEqual(raster.shape, (3, 100))
        self.assertEqual(meta["nadir_pixel_x"], 50.0)

        # Row 1 has starboard missing -> columns [50..99] are 0
        self.assertTrue(np.all(raster[1, 50:100] == 0))
        self.assertGreater(raster[1, 0:50].max(), 0)

        # Row 2 has port missing -> columns [0..49] are 0
        self.assertTrue(np.all(raster[2, 0:50] == 0))
        self.assertGreater(raster[2, 50:100].max(), 0)

        self.assertTrue(any("missing Port channel" in w for w in meta["warnings"]))
        self.assertTrue(any("missing Starboard channel" in w for w in meta["warnings"]))

    def test_09_max_pings(self):
        """
        Support max_pings parameter for strict memory bounding.
        """
        pings = [{0: np.ones(40, dtype=np.float32), 1: np.ones(40, dtype=np.float32)} for _ in range(25)]

        # max_pings = 5
        raster, meta = SonarRasterBuilder.assemble_scanlines(pings, max_pings=5)
        self.assertEqual(raster.shape, (5, 80))
        self.assertEqual(meta["total_pings"], 5)

        # max_pings = 0
        raster_zero, meta_zero = SonarRasterBuilder.assemble_scanlines(pings, max_pings=0)
        self.assertEqual(raster_zero.shape, (0, 0))
        self.assertEqual(meta_zero["total_pings"], 0)

        # max_pings negative -> ValueError
        with self.assertRaises(ValueError):
            SonarRasterBuilder.assemble_scanlines(pings, max_pings=-1)

        # max_pings invalid type -> TypeError
        with self.assertRaises(TypeError):
            SonarRasterBuilder.assemble_scanlines(pings, max_pings="5")  # type: ignore

    def test_10_nan_inf_handling(self):
        """
        Safely sanitize NaN, +Inf, -Inf, and negative values.
        Output raster must be finite uint8 without runtime errors.
        """
        corrupt_samples = np.array([10.0, np.nan, np.inf, -np.inf, -50.0, 80.0], dtype=np.float32)
        cleaned = SonarRasterBuilder.sanitize_samples(corrupt_samples)

        self.assertEqual(len(cleaned), 6)
        self.assertTrue(np.isfinite(cleaned).all())
        self.assertEqual(cleaned[1], 0.0)  # NaN -> 0.0
        self.assertEqual(cleaned[2], 0.0)  # +Inf -> 0.0
        self.assertEqual(cleaned[3], 0.0)  # -Inf -> 0.0
        self.assertEqual(cleaned[4], 0.0)  # -50.0 -> 0.0
        self.assertEqual(cleaned[0], 10.0)
        self.assertEqual(cleaned[5], 80.0)

        # Full raster assembly with corrupt samples
        pings = [{0: corrupt_samples, 1: corrupt_samples}]
        raster, meta = SonarRasterBuilder.assemble_scanlines(pings)
        self.assertEqual(raster.shape, (1, 12))
        self.assertEqual(raster.dtype, np.uint8)
        self.assertTrue(np.isfinite(raster).all())

    def test_11_deterministic_normalization(self):
        """
        Normalization must be 100% deterministic and robust against extreme outliers.
        """
        base_arr = np.random.uniform(5.0, 100.0, (10, 80)).astype(np.float32)

        norm1 = SonarRasterBuilder.normalize_intensity(base_arr)
        norm2 = SonarRasterBuilder.normalize_intensity(base_arr)
        self.assertTrue(np.array_equal(norm1, norm2))

        # All-zeros matrix
        zeros_arr = np.zeros((5, 50), dtype=np.float32)
        norm_zeros = SonarRasterBuilder.normalize_intensity(zeros_arr)
        self.assertEqual(norm_zeros.shape, (5, 50))
        self.assertTrue(np.all(norm_zeros == 0))

        # Uniform matrix
        uniform_arr = np.full((5, 50), 42.0, dtype=np.float32)
        norm_uniform = SonarRasterBuilder.normalize_intensity(uniform_arr)
        self.assertEqual(norm_uniform.shape, (5, 50))
        self.assertEqual(norm_uniform.dtype, np.uint8)

        # Outlier spike resistance (e.g. 1 sample = 1,000,000)
        # Percentile clipping must keep normal values visible rather than crushing to 0
        arr_with_spike = base_arr.copy()
        arr_with_spike[0, 0] = 1_000_000.0
        norm_spike = SonarRasterBuilder.normalize_intensity(arr_with_spike)
        # Check that median/mean of non-spike samples is non-zero
        self.assertGreater(np.median(norm_spike), 0)

    def test_12_correct_raster_dimensions(self):
        """
        Verify that raster dimensions strictly correspond to (total_pings, sample_width).
        """
        test_cases = [
            (3, 40, 40, (3, 80)),
            (5, 100, 50, (5, 150)),
            (1, 200, 200, (1, 400)),
        ]
        for num_p, p_len, s_len, expected_shape in test_cases:
            pings = [{0: np.ones(p_len, dtype=np.float32), 1: np.ones(s_len, dtype=np.float32)} for _ in range(num_p)]
            raster, meta = SonarRasterBuilder.assemble_scanlines(pings)
            self.assertEqual(raster.shape, expected_shape)
            self.assertEqual(meta["total_pings"], expected_shape[0])
            self.assertEqual(meta["sample_width"], expected_shape[1])

    def test_13_correct_nadir_placement(self):
        """
        Verify nadir pixel location under symmetric, asymmetric, and single-channel modes.
        """
        # Symmetric dual-channel
        pings_sym = [{0: np.ones(50, dtype=np.float32), 1: np.ones(50, dtype=np.float32)}]
        _, meta_sym = SonarRasterBuilder.assemble_scanlines(pings_sym)
        self.assertEqual(meta_sym["nadir_pixel_x"], 50.0)

        # Asymmetric dual-channel (40 port, 75 stbd -> width 115)
        pings_asym = [{0: np.ones(40, dtype=np.float32), 1: np.ones(75, dtype=np.float32)}]
        _, meta_asym = SonarRasterBuilder.assemble_scanlines(pings_asym)
        self.assertEqual(meta_asym["nadir_pixel_x"], 40.0)
        self.assertEqual(meta_asym["sample_width"], 115)

        # Port-only (width 60) -> nadir at right edge
        pings_port = [{0: np.ones(60, dtype=np.float32)}]
        _, meta_port = SonarRasterBuilder.assemble_scanlines(pings_port, requested_channels=[0])
        self.assertEqual(meta_port["nadir_pixel_x"], 60.0)

        # Starboard-only (width 80) -> nadir at left edge
        pings_stbd = [{1: np.ones(80, dtype=np.float32)}]
        _, meta_stbd = SonarRasterBuilder.assemble_scanlines(pings_stbd, requested_channels=[1])
        self.assertEqual(meta_stbd["nadir_pixel_x"], 0.0)

    def test_14_invalid_channel_selection(self):
        """
        Validate error handling for negative, empty, non-existent, or invalid channel selections.
        """
        pings = [{0: np.ones(50, dtype=np.float32), 1: np.ones(50, dtype=np.float32)}]

        # Negative channel index -> ValueError
        with self.assertRaises(ValueError):
            SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[-1])

        # Empty channels list -> ValueError
        with self.assertRaises(ValueError):
            SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[])

        # Non-integer channels -> TypeError
        with self.assertRaises(TypeError):
            SonarRasterBuilder.assemble_scanlines(pings, requested_channels=["port"])  # type: ignore

        # Valid non-existent channel ID (e.g. 99) -> safe empty raster with explicit warning
        raster, meta = SonarRasterBuilder.assemble_scanlines(pings, requested_channels=[99])
        self.assertEqual(raster.shape, (1, 0))
        self.assertEqual(meta["sample_width"], 0)
        self.assertTrue(any("Requested channel 99 is not present" in w for w in meta["warnings"]))

    def test_15_no_fabricated_physical_units(self):
        """
        Verify that physical resolution and slant range are strictly None when unrecorded,
        and accurately computed when valid header telemetry is provided.
        """
        pings = [{0: np.ones(100, dtype=np.float32), 1: np.ones(100, dtype=np.float32)}]

        # Case A: Slant range missing / unlogged
        _, meta_none = SonarRasterBuilder.assemble_scanlines(pings, slant_ranges=None)
        self.assertIsNone(meta_none["slant_range_m"])
        self.assertIsNone(meta_none["meters_per_pixel"])
        self.assertTrue(any("meters_per_pixel cannot be determined" in w for w in meta_none["warnings"]))

        # Case B: Slant range non-positive sentinel (e.g. 0.0 or -1.0)
        _, meta_zero = SonarRasterBuilder.assemble_scanlines(pings, slant_ranges=[0.0])
        self.assertIsNone(meta_zero["slant_range_m"])
        self.assertIsNone(meta_zero["meters_per_pixel"])

        # Case C: Valid slant range provided (50.0m range with 100 samples per side -> 0.5 m/px)
        _, meta_valid = SonarRasterBuilder.assemble_scanlines(pings, slant_ranges=[50.0])
        self.assertEqual(meta_valid["slant_range_m"], 50.0)
        self.assertEqual(meta_valid["meters_per_pixel"], 0.5)

    def test_16_xtf_parser_waterfall_integration(self):
        """
        Verify XtfSonarParser.build_waterfall_raster delegates cleanly to SonarRasterBuilder.
        Uses specification-compliant synthetic XTF buffer.
        """
        buf = build_synthetic_xtf_binary(num_pings=6, samples_per_chan=80)
        parser = XtfSonarParser()

        # 1. Default dual-channel
        raster, meta = parser.build_waterfall_raster(buf)
        self.assertEqual(raster.shape, (6, 160))
        self.assertEqual(raster.dtype, np.uint8)
        self.assertEqual(meta["format"], "XTF")
        self.assertEqual(meta["channel_layout"], "port_nadir_starboard")
        self.assertEqual(meta["nadir_pixel_x"], 80.0)

        # 2. Bounded max_pings
        raster_sub, meta_sub = parser.build_waterfall_raster(buf, max_pings=3)
        self.assertEqual(raster_sub.shape, (3, 160))
        self.assertEqual(meta_sub["total_pings"], 3)

        # 3. Single-channel selection
        raster_p, meta_p = parser.build_waterfall_raster(buf, channels=[0])
        self.assertEqual(raster_p.shape, (6, 80))
        self.assertEqual(meta_p["channel_layout"], "port_only")

        # 4. Invalid channel selection raises ValueError
        with self.assertRaises(ValueError):
            parser.build_waterfall_raster(buf, channels=[-1])


if __name__ == "__main__":
    unittest.main()
