"""Open-set anomaly branch (Branch 2) for MarineScan.

Wraps the PatchCore feature-space detector as a lazily-loaded singleton. Generates
unclassified anomaly candidates (class 5) that are merged with the YOLO candidates and
carry a P_CAE score into confidence fusion. Loads on first use and degrades gracefully:
if torch, the backbone, or the seabed bank is unavailable, the branch disables itself
and returns no candidates, leaving the rest of the pipeline unaffected.
"""

import logging
from pathlib import Path
from typing import Dict, List

import numpy as np

from app.core.config import settings

logger = logging.getLogger("marinescan.services.anomaly")


def _iou(a: Dict, b: Dict) -> float:
    ax0, ay0, ax1, ay1 = a["x_min"], a["y_min"], a["x_max"], a["y_max"]
    bx0, by0, bx1, by1 = b["x_min"], b["y_min"], b["x_max"], b["y_max"]
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / ua if ua > 0 else 0.0


class AnomalyService:
    """Feature-space open-set detector; feeds candidates + P_CAE into the fusion engine."""

    def __init__(self) -> None:
        self._detector = None
        self._loaded = False          # load attempted
        self.available = False        # detector ready

    def _resolve_asset(self, configured_path: str) -> Path:
        """Find a bundled asset independent of the current working directory."""
        configured = Path(configured_path)
        pkg_local = Path(__file__).resolve().parent.parent / "ml" / "anomaly" / configured.name
        for cand in (configured, Path.cwd() / configured, pkg_local):
            if cand.exists():
                return cand
        return configured

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not settings.ANOMALY_ENABLED:
            logger.info("Anomaly branch disabled via ANOMALY_ENABLED=False.")
            return
        method = (settings.ANOMALY_METHOD or "patchcore").lower()
        try:
            if method == "feature_ae":
                asset = self._resolve_asset(settings.ANOMALY_FEATAE_PATH)
                if not asset.exists():
                    logger.warning("Feature-AE checkpoint not found at %s; branch disabled.", asset)
                    return
                from app.ml.anomaly.feature_ae import FeatureAEDetector
                self._detector = FeatureAEDetector(asset)
            else:
                asset = self._resolve_asset(settings.ANOMALY_BANK_PATH)
                if not asset.exists():
                    logger.warning("Anomaly bank not found at %s; branch disabled.", asset)
                    return
                from app.ml.anomaly.patchcore import PatchCoreDetector
                self._detector = PatchCoreDetector(asset)
            self.available = True
            logger.info("Anomaly branch loaded (%s, device=%s).", method, self._detector.device)
        except Exception as exc:  # torch/backbone/asset problems must not break the pipeline
            logger.warning("Anomaly branch failed to load (%s); disabled.", exc)

    def detect_candidates(self, image_bgr: np.ndarray) -> List[Dict]:
        """Anomaly candidate dicts (empty list if the branch is unavailable)."""
        self._ensure_loaded()
        if not self.available:
            return []
        try:
            return self._detector.detect(
                image_bgr,
                thr_key=settings.ANOMALY_THRESHOLD_KEY,
                min_area=settings.ANOMALY_MIN_AREA,
            )
        except Exception as exc:
            logger.warning("Anomaly detection failed (%s); returning no candidates.", exc)
            return []

    def merge_with(self, yolo_candidates: List[Dict], image_bgr: np.ndarray,
                   iou_dedup: float = 0.3) -> List[Dict]:
        """Append anomaly candidates that don't overlap an existing YOLO detection."""
        anomalies = self.detect_candidates(image_bgr)
        if not anomalies:
            return yolo_candidates
        kept = [a for a in anomalies
                if all(_iou(a["bbox"], y["bbox"]) < iou_dedup for y in yolo_candidates)]
        if kept:
            logger.info("Anomaly branch added %d open-set candidate(s).", len(kept))
        return yolo_candidates + kept


anomaly_service = AnomalyService()
