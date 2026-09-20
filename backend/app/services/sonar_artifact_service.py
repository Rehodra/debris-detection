"""
Sonar Waterfall Raster Artifact Persistence Service for MarineScan.
Manages the lifecycle, deterministic storage, retrieval, and cleanup of
lossless PNG acoustic waterfall raster artifacts linked to unique analysis IDs.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

from app.core.config import settings

logger = logging.getLogger("marinescan.services.sonar_artifact")


class SonarArtifactService:
    """
    Dedicated storage and retrieval service for raw sonar waterfall raster artifacts.
    Guarantees 1:1 deterministic association between analysis ID and its acoustic raster.
    """

    def __init__(self, storage_dir: Optional[Union[str, Path]] = None) -> None:
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
        else:
            configured_dir = getattr(settings, "SONAR_ARTIFACT_DIR", "pred_img/sonar_artifacts")
            base_backend_dir = Path(__file__).resolve().parents[2]
            p = Path(configured_dir)
            if p.is_absolute():
                self.storage_dir = p
            else:
                self.storage_dir = base_backend_dir / p

        self.storage_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_id(analysis_id: str) -> str:
        """Sanitize analysis ID for safe filesystem naming while preserving uniqueness."""
        return re.sub(r"[^a-zA-Z0-9_\-]", "_", str(analysis_id))

    def _png_path(self, analysis_id: str) -> Path:
        safe_id = self._sanitize_id(analysis_id)
        return self.storage_dir / f"sonar_raster_{safe_id}.png"

    def _meta_path(self, analysis_id: str) -> Path:
        safe_id = self._sanitize_id(analysis_id)
        return self.storage_dir / f"sonar_raster_{safe_id}.json"

    def _track_path(self, analysis_id: str) -> Path:
        safe_id = self._sanitize_id(analysis_id)
        return self.storage_dir / f"sonar_track_{safe_id}.json"

    def save_track_artifact(
        self,
        analysis_id: str,
        track: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Persist an ordered SonarNavigationTrack to artifact storage as a standalone JSON artifact.
        """
        if track is None:
            raise ValueError(f"Cannot save empty navigation track for analysis '{analysis_id}'.")

        if hasattr(track, "model_dump"):
            track_dict = track.model_dump(mode="json")
        elif isinstance(track, dict):
            track_dict = track
        else:
            track_dict = dict(track)

        artifact_id = f"track_{analysis_id}"
        relative_url = f"/api/v1/analyses/{analysis_id}/sonar/track"

        payload: Dict[str, Any] = {
            "artifact_id": artifact_id,
            "analysis_id": analysis_id,
            "media_type": "application/json",
            "relative_url": relative_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            **track_dict,
        }

        if metadata:
            for k, v in metadata.items():
                if k not in payload:
                    payload[k] = v

        track_file = self._track_path(analysis_id)
        track_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        logger.info(
            "Persisted sonar navigation track artifact %s (%d pings) for analysis %s",
            artifact_id,
            payload.get("total_pings", 0),
            analysis_id,
        )

        return {
            "artifact_id": artifact_id,
            "analysis_id": analysis_id,
            "media_type": "application/json",
            "relative_url": relative_url,
            "local_path": str(track_file),
            "total_pings": payload.get("total_pings", 0),
            "available_navigation_pings": payload.get("available_navigation_pings", 0),
        }

    def get_track_artifact(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Return the parsed track dictionary for the given analysis ID, if available."""
        track_file = self._track_path(analysis_id)
        if track_file.exists() and track_file.is_file():
            try:
                return json.loads(track_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Error reading track artifact %s: %s", track_file, exc)
        return None

    def has_track_artifact(self, analysis_id: str) -> bool:
        """Check whether a navigation track artifact exists for this analysis ID."""
        track_file = self._track_path(analysis_id)
        return track_file.exists() and track_file.is_file()

    def save_waterfall_artifact(
        self,
        analysis_id: str,
        raster: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Encode an acoustic waterfall raster as PNG and persist it to artifact storage.
        Also persists sidecar JSON metadata for standalone traceability.
        """
        if raster is None or not isinstance(raster, np.ndarray) or raster.size == 0:
            raise ValueError(f"Cannot save empty or invalid raster for analysis '{analysis_id}'.")

        orig_h, orig_w = raster.shape[:2]
        if orig_h == 0 or orig_w == 0:
            raise ValueError(f"Raster dimensions must be positive, got shape {raster.shape}.")

        # Ensure uint8
        if raster.dtype != np.uint8:
            raster_uint8 = np.clip(raster, 0, 255).astype(np.uint8)
        else:
            raster_uint8 = raster

        success, encoded = cv2.imencode(".png", raster_uint8)
        if not success or encoded is None:
            raise RuntimeError(f"Failed to encode sonar raster to PNG for analysis '{analysis_id}'.")

        png_bytes = encoded.tobytes()
        png_file = self._png_path(analysis_id)
        meta_file = self._meta_path(analysis_id)

        png_file.write_bytes(png_bytes)

        artifact_id = f"art_{analysis_id}"
        relative_url = f"/api/v1/analyses/{analysis_id}/sonar/raster"

        artifact_meta: Dict[str, Any] = {
            "artifact_id": artifact_id,
            "analysis_id": analysis_id,
            "media_type": "image/png",
            "waterfall_width": orig_w,
            "waterfall_height": orig_h,
            "file_size_bytes": len(png_bytes),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "relative_url": relative_url,
            "local_path": str(png_file),
        }

        if metadata:
            for k, v in metadata.items():
                if k not in artifact_meta:
                    artifact_meta[k] = v

        try:
            meta_file.write_text(json.dumps(artifact_meta, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not write sidecar metadata for analysis %s: %s", analysis_id, exc)

        logger.info(
            "Persisted sonar waterfall artifact %s (%dx%d, %d bytes) for analysis %s",
            artifact_id,
            orig_w,
            orig_h,
            len(png_bytes),
            analysis_id,
        )

        return artifact_meta

    def get_artifact_path(self, analysis_id: str) -> Optional[Path]:
        """Return the physical path to the stored raster PNG if it exists, else None."""
        p = self._png_path(analysis_id)
        return p if p.exists() and p.is_file() else None

    def get_artifact_bytes(self, analysis_id: str) -> Optional[bytes]:
        """Read and return the PNG binary bytes for the given analysis ID, if available."""
        path = self.get_artifact_path(analysis_id)
        if path is not None:
            try:
                return path.read_bytes()
            except Exception as exc:
                logger.error("Error reading artifact file %s: %s", path, exc)
        return None

    def get_artifact_metadata(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Return the sidecar metadata dictionary for the given analysis ID, if available."""
        meta_file = self._meta_path(analysis_id)
        if meta_file.exists() and meta_file.is_file():
            try:
                return json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Error reading sidecar metadata %s: %s", meta_file, exc)
        return None

    def has_artifact(self, analysis_id: str) -> bool:
        """Check whether a physical PNG raster artifact exists for this analysis ID."""
        return self.get_artifact_path(analysis_id) is not None

    def delete_artifact(self, analysis_id: str) -> bool:
        """Remove PNG raster artifact, sidecar metadata file, and navigation track for an analysis."""
        deleted = False
        png_file = self._png_path(analysis_id)
        if png_file.exists():
            try:
                png_file.unlink()
                deleted = True
            except Exception as exc:
                logger.warning("Could not unlink artifact PNG %s: %s", png_file, exc)

        meta_file = self._meta_path(analysis_id)
        if meta_file.exists():
            try:
                meta_file.unlink()
                deleted = True
            except Exception as exc:
                logger.warning("Could not unlink artifact metadata %s: %s", meta_file, exc)

        track_file = self._track_path(analysis_id)
        if track_file.exists():
            try:
                track_file.unlink()
                deleted = True
            except Exception as exc:
                logger.warning("Could not unlink artifact track %s: %s", track_file, exc)

        return deleted

    def cleanup_old_artifacts(
        self,
        max_age_seconds: Optional[float] = None,
        max_count: Optional[int] = None,
    ) -> int:
        """
        Prune older artifact files to prevent uncontrolled disk growth.
        Supports pruning by age (seconds) and/or limiting total artifact count.
        Returns total count of removed artifacts.
        """
        png_files = sorted(
            self.storage_dir.glob("sonar_raster_*.png"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        deleted_count = 0
        now = time.time()

        for idx, png_file in enumerate(png_files):
            should_delete = False

            if max_age_seconds is not None:
                age = now - png_file.stat().st_mtime
                if age > max_age_seconds:
                    should_delete = True

            if max_count is not None and idx >= max_count:
                should_delete = True

            if should_delete:
                try:
                    png_file.unlink()
                    meta_file = png_file.with_suffix(".json")
                    if meta_file.exists():
                        meta_file.unlink()
                    # Also remove corresponding track file if present
                    safe_id = png_file.stem.replace("sonar_raster_", "")
                    track_file = self.storage_dir / f"sonar_track_{safe_id}.json"
                    if track_file.exists():
                        track_file.unlink()
                    deleted_count += 1
                except Exception as exc:
                    logger.warning("Failed to cleanup artifact %s: %s", png_file, exc)

        return deleted_count


# Global singleton instance
sonar_artifact_service = SonarArtifactService()
