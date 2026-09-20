"""
Acoustic Waterfall Raster Assembly and Normalization Engine for MarineScan.
Converts raw sidescan sonar channel returns into aligned, normalized 2D matrices.

Contract & Coordinate System:
  - Array Shape: (H, W), dtype: uint8 [0, 255].
  - Height (H): Sequential acoustic pings along the vehicle trackline (row 0 = earliest ping).
  - Width (W): Across-track acoustic range bins.
  - Channel Arrangement:
      - Dual-channel (Port + Starboard):
          [ Port (far-range → near-nadir) | Nadir Line | Starboard (near-nadir → far-range) ]
          Port channel samples radiate outwards from nadir to the left; they are horizontally
          reversed so that the center column represents the zero across-track nadir ground track.
      - Port-only:
          [ Port (far-range → near-nadir) ] — Nadir is at the rightmost boundary.
      - Starboard-only:
          [ Starboard (near-nadir → far-range) ] — Nadir is at the leftmost boundary.
  - Normalization:
      Deterministic 1st-to-99th percentile intensity clipping mapped to uint8 [0, 255].
      Does not apply ad-hoc CLAHE or enhancement (reserved for preprocessing service).
  - Physical Units:
      If slant range is missing or <= 0, slant_range_m and meters_per_pixel are strictly None.
      No physical units are fabricated.
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np


class SonarRasterBuilder:
    """
    Pure-logic builder for assembling and normalizing acoustic waterfall matrices.
    Independent of specific file formats; operates on decoded channel sample buffers.
    """

    @staticmethod
    def sanitize_samples(samples: np.ndarray) -> np.ndarray:
        """
        Sanitize raw acoustic samples by replacing NaN, +Inf, -Inf, and negative values.
        Returns a clean float32 1D array.
        """
        if samples is None or samples.size == 0:
            return np.zeros(0, dtype=np.float32)

        arr = np.asarray(samples, dtype=np.float32)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        # Rectify any remaining negative values
        arr = np.maximum(arr, 0.0)
        return arr

    @classmethod
    def normalize_intensity(cls, matrix: np.ndarray) -> np.ndarray:
        """
        Deterministically normalize a 2D float matrix to uint8 [0, 255].
        Uses 1st to 99th percentile clipping of positive acoustic returns.
        """
        if matrix.size == 0:
            return np.zeros(matrix.shape, dtype=np.uint8)

        # Sanitize entire matrix
        clean = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
        clean = np.maximum(clean, 0.0)

        positive_vals = clean[clean > 0]
        if positive_vals.size > 0:
            p1 = float(np.percentile(positive_vals, 1))
            p99 = float(np.percentile(positive_vals, 99))

            if p99 > p1:
                scaled = np.clip((clean - p1) / (p99 - p1) * 255.0, 0, 255)
                return scaled.astype(np.uint8)
            else:
                max_val = float(np.max(clean))
                if max_val > 0:
                    scaled = np.clip(clean / max_val * 255.0, 0, 255)
                    return scaled.astype(np.uint8)

        return np.clip(clean, 0, 255).astype(np.uint8)

    @classmethod
    def assemble_scanlines(
        cls,
        pings_channels: List[Dict[int, np.ndarray]],
        requested_channels: Optional[List[int]] = None,
        slant_ranges: Optional[List[Optional[float]]] = None,
        max_pings: Optional[int] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Assemble a sequence of per-ping channel dictionaries into an aligned, normalized 2D raster.

        Contract & Output Specification:
          - raster (np.ndarray): 2D array of shape (H, W), dtype uint8 [0, 255].
          - Height (H): Number of acoustic pings represented (along-track direction, row 0 = first ping).
          - Width (W): Total acoustic range bins across all included channels.
          - Channel Arrangement:
              * Dual-channel ([0, 1]): Port (far-to-nadir) | Nadir Column | Starboard (nadir-to-far).
                Port samples are reversed horizontally so that nadir is aligned at the center.
              * Port-only ([0]): Port (far-to-nadir), nadir is at the right edge (x = W).
              * Starboard-only ([1]): Starboard (nadir-to-far), nadir is at the left edge (x = 0).
          - Nadir Position (nadir_pixel_x):
              * Float or None. In dual-channel, exactly equal to max_port_len.
          - Spatial Resolution (meters_per_pixel):
              * Average slant range divided by samples per side. Strictly None if slant range is unrecorded.
          - Range Information (slant_range_m):
              * Average recorded slant range in meters. Strictly None if unrecorded.
          - Warnings:
              * List of human-readable warnings regarding missing channels, varying lengths, unrecorded range, etc.

        Args:
            pings_channels: List of dicts mapping channel_id (0: port, 1: stbd) to 1D sample arrays.
            requested_channels: Specific channel IDs to include (e.g. [0], [1], or [0, 1]).
            slant_ranges: Optional list of slant ranges (meters) corresponding to each ping.
            max_pings: Optional limit on the number of pings to assemble for memory bounding.

        Returns:
            Tuple of:
              - 2D np.ndarray: uint8 normalized raster of shape (H, W).
              - Dict[str, Any]: Spatial metadata and layout description.

        Raises:
            ValueError: If requested_channels is empty, contains negative IDs, or max_pings < 0.
            TypeError: If requested_channels or max_pings are of invalid types.
        """
        warnings: List[str] = []

        # Validate requested_channels if provided
        if requested_channels is not None:
            if not isinstance(requested_channels, (list, tuple)):
                raise TypeError(f"requested_channels must be a list or tuple, got {type(requested_channels).__name__}")
            if len(requested_channels) == 0:
                raise ValueError("Invalid channel selection: requested channels list cannot be empty.")
            for c in requested_channels:
                if not isinstance(c, int) or isinstance(c, bool):
                    raise TypeError(f"Channel IDs must be integers, got {type(c).__name__}")
                if c < 0:
                    raise ValueError(f"Invalid channel selection: channel IDs must be non-negative integers, got {c}")

        # Validate and apply max_pings memory bound
        if max_pings is not None:
            if not isinstance(max_pings, int) or isinstance(max_pings, bool):
                raise TypeError(f"max_pings must be an integer, got {type(max_pings).__name__}")
            if max_pings < 0:
                raise ValueError(f"max_pings must be a non-negative integer, got {max_pings}")
            pings_channels = pings_channels[:max_pings]
            if slant_ranges is not None:
                slant_ranges = slant_ranges[:max_pings]

        if not pings_channels:
            return np.zeros((0, 0), dtype=np.uint8), {
                "nadir_pixel_x": None,
                "meters_per_pixel": None,
                "slant_range_m": None,
                "total_pings": 0,
                "sample_width": 0,
                "channels_included": list(requested_channels) if requested_channels is not None else [],
                "channel_layout": "empty",
                "dtype": "uint8",
                "intensity_min": 0,
                "intensity_max": 0,
                "intensity_mean": 0.0,
                "warnings": ["No acoustic pings provided."],
            }

        # 1. Determine active channel configuration
        if requested_channels is not None:
            active_channels = list(requested_channels)
            # Check if any requested channel exists across the pings
            all_present = set().union(*(p.keys() for p in pings_channels if p))
            for req in active_channels:
                if req not in all_present:
                    warnings.append(f"Requested channel {req} is not present in any ping.")
        else:
            # Auto-detect channels present across pings
            all_present = sorted(set().union(*(p.keys() for p in pings_channels if p)))
            if 0 in all_present and 1 in all_present:
                active_channels = [0, 1]
            elif all_present:
                active_channels = all_present
            else:
                active_channels = [0, 1]

        is_dual = (active_channels == [0, 1])
        is_port_only = (active_channels == [0])
        is_stbd_only = (active_channels == [1])

        # 2. Compute maximum sample lengths per channel for consistent alignment
        max_port_len = 0
        max_stbd_len = 0
        max_other_lens: Dict[int, int] = {c: 0 for c in active_channels}

        for ping in pings_channels:
            if not ping:
                continue
            for ch_id in active_channels:
                samples = ping.get(ch_id)
                s_len = len(samples) if samples is not None else 0
                if ch_id == 0:
                    max_port_len = max(max_port_len, s_len)
                elif ch_id == 1:
                    max_stbd_len = max(max_stbd_len, s_len)
                max_other_lens[ch_id] = max(max_other_lens[ch_id], s_len)

        num_pings = len(pings_channels)

        # 3. Assemble scanlines with alignment preserving straight nadir
        if is_dual:
            total_width = max_port_len + max_stbd_len
            if total_width == 0:
                warnings.append("Dual-channel requested but all sample buffers are 0 bytes.")
                return np.zeros((num_pings, 0), dtype=np.uint8), {
                    "nadir_pixel_x": None,
                    "meters_per_pixel": None,
                    "slant_range_m": None,
                    "total_pings": num_pings,
                    "sample_width": 0,
                    "channels_included": [0, 1],
                    "channel_layout": "dual_empty",
                    "dtype": "uint8",
                    "intensity_min": 0,
                    "intensity_max": 0,
                    "intensity_mean": 0.0,
                    "warnings": warnings,
                }

            unnorm_matrix = np.zeros((num_pings, total_width), dtype=np.float32)
            nadir_col = float(max_port_len)
            channel_layout = "port_nadir_starboard"

            for i, ping in enumerate(pings_channels):
                if not ping:
                    warnings.append(f"Ping {i} is empty; zero-filled.")
                    continue

                # Port channel: reversed, placed in [max_port_len - len : max_port_len]
                # Right-aligned against nadir so that nadir column remains perfectly fixed!
                port_raw = ping.get(0)
                if port_raw is not None and len(port_raw) > 0:
                    port_clean = cls.sanitize_samples(port_raw)
                    p_len = len(port_clean)
                    # Flip port so sample 0 (nadir) is adjacent to nadir column
                    port_flipped = port_clean[::-1]
                    start_col = max_port_len - p_len
                    unnorm_matrix[i, start_col:max_port_len] = port_flipped
                    if p_len < max_port_len:
                        warnings.append(f"Ping {i} Port sample count ({p_len}) shorter than max ({max_port_len}); far-range padded.")
                elif max_port_len > 0:
                    warnings.append(f"Ping {i} is missing Port channel; zero-padded.")

                # Starboard channel: placed in [max_port_len : max_port_len + len]
                # Left-aligned against nadir
                stbd_raw = ping.get(1)
                if stbd_raw is not None and len(stbd_raw) > 0:
                    stbd_clean = cls.sanitize_samples(stbd_raw)
                    s_len = len(stbd_clean)
                    unnorm_matrix[i, max_port_len : max_port_len + s_len] = stbd_clean
                    if s_len < max_stbd_len:
                        warnings.append(f"Ping {i} Starboard sample count ({s_len}) shorter than max ({max_stbd_len}); far-range padded.")
                elif max_stbd_len > 0:
                    warnings.append(f"Ping {i} is missing Starboard channel; zero-padded.")

        elif is_port_only:
            total_width = max_port_len
            nadir_col = float(total_width) if total_width > 0 else None
            channel_layout = "port_only"
            unnorm_matrix = np.zeros((num_pings, total_width), dtype=np.float32)

            for i, ping in enumerate(pings_channels):
                if not ping:
                    continue
                port_raw = ping.get(0)
                if port_raw is not None and len(port_raw) > 0:
                    port_clean = cls.sanitize_samples(port_raw)
                    p_len = len(port_clean)
                    # Flip so nadir is on the right boundary
                    port_flipped = port_clean[::-1]
                    unnorm_matrix[i, total_width - p_len : total_width] = port_flipped

        elif is_stbd_only:
            total_width = max_stbd_len
            nadir_col = 0.0 if total_width > 0 else None
            channel_layout = "starboard_only"
            unnorm_matrix = np.zeros((num_pings, total_width), dtype=np.float32)

            for i, ping in enumerate(pings_channels):
                if not ping:
                    continue
                stbd_raw = ping.get(1)
                if stbd_raw is not None and len(stbd_raw) > 0:
                    stbd_clean = cls.sanitize_samples(stbd_raw)
                    unnorm_matrix[i, : len(stbd_clean)] = stbd_clean

        else:
            # Custom / multi-channel layout
            total_width = sum(max_other_lens.values())
            nadir_col = None
            channel_layout = "custom"
            unnorm_matrix = np.zeros((num_pings, total_width), dtype=np.float32)

            col_offsets: Dict[int, int] = {}
            curr = 0
            for ch_id in active_channels:
                col_offsets[ch_id] = curr
                curr += max_other_lens[ch_id]

            for i, ping in enumerate(pings_channels):
                if not ping:
                    continue
                for ch_id in active_channels:
                    raw_s = ping.get(ch_id)
                    if raw_s is not None and len(raw_s) > 0:
                        clean_s = cls.sanitize_samples(raw_s)
                        c_start = col_offsets[ch_id]
                        unnorm_matrix[i, c_start : c_start + len(clean_s)] = clean_s

        # 4. Deterministic Normalization
        raster = cls.normalize_intensity(unnorm_matrix)

        # 5. Compute real physical resolution without fabrication
        valid_ranges = [r for r in (slant_ranges or []) if r is not None and r > 0.0]
        if valid_ranges:
            avg_range = float(np.mean(valid_ranges))
            slant_range_m = round(avg_range, 2)
            # Effective samples per side
            samples_per_side = max_port_len if max_port_len > 0 else (max_stbd_len if max_stbd_len > 0 else total_width)
            if samples_per_side > 0:
                meters_per_pixel = round(avg_range / float(samples_per_side), 4)
            else:
                meters_per_pixel = None
        else:
            slant_range_m = None
            meters_per_pixel = None
            warnings.append("Slant range unavailable in acoustic headers; meters_per_pixel cannot be determined.")

        min_val = int(np.min(raster)) if raster.size > 0 else 0
        max_val = int(np.max(raster)) if raster.size > 0 else 0
        mean_val = round(float(np.mean(raster)), 2) if raster.size > 0 else 0.0

        metadata = {
            "nadir_pixel_x": nadir_col,
            "meters_per_pixel": meters_per_pixel,
            "slant_range_m": slant_range_m,
            "total_pings": num_pings,
            "sample_width": total_width,
            "channels_included": active_channels,
            "channel_layout": channel_layout,
            "dtype": "uint8",
            "intensity_min": min_val,
            "intensity_max": max_val,
            "intensity_mean": mean_val,
            "warnings": warnings,
        }

        return raster, metadata
