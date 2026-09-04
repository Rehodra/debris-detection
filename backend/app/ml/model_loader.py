"""
Model loader singleton for MarineScan Debris Detection model.
Loads and caches the Ultralytics YOLO model with device selection,
path resolution, and warmup inference.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any

import numpy as np
import torch
from ultralytics import YOLO
from app.core.config import settings
from app.ml.class_map import CLASS_NAMES



logger = logging.getLogger("marinescan.ml.model_loader")


class ModelLoader:
    """Thread-safe singleton model loader for YOLO debris detection."""

    _instance: Optional["ModelLoader"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ModelLoader":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ModelLoader, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._model: Optional[YOLO] = None
        self._model_path: Optional[Path] = None
        self._device: str = self._select_optimal_device()
        self._is_loaded: bool = False
        self._load_duration_ms: float = 0.0
        self._model_lock = threading.Lock()
        self._initialized = True

    @staticmethod
    def _select_optimal_device() -> str:
        """Detect best available hardware accelerator."""
        if torch.cuda.is_available():
            return "cuda"
        # Apple Silicon MPS
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            try:
                # Test MPS support with a small tensor
                _ = torch.zeros(1, device="mps")
                return "mps"
            except Exception:
                pass
        return "cpu"

    @classmethod
    def resolve_model_path(cls, candidate_path: Optional[str] = None) -> Path:
        """
        Resolve the absolute path to the weights file across known project locations.
        """
        search_paths = []
        target = candidate_path or settings.MODEL_PATH

        if target:
            search_paths.append(Path(target))

        # Check relative to backend/app/ml/weights/best.pt
        ml_dir = Path(__file__).resolve().parent
        search_paths.append(ml_dir / "weights" / "best.pt")

        # Check relative to repository root (ml/weights/best.pt)
        repo_root = ml_dir.parents[2]  # backend/app/ml -> app -> backend -> repo root
        search_paths.append(repo_root / "ml" / "weights" / "best.pt")
        search_paths.append(repo_root / "backend" / "app" / "ml" / "weights" / "best.pt")

        # Current working directory
        cwd = Path.cwd()
        search_paths.append(cwd / "ml" / "weights" / "best.pt")
        search_paths.append(cwd / "backend" / "app" / "ml" / "weights" / "best.pt")
        search_paths.append(cwd / "weights" / "best.pt")

        for path in search_paths:
            if path.is_file():
                try:
                    return Path(os.path.relpath(path, cwd))
                except Exception:
                    return path.resolve()

        # If not found yet, raise or return the primary target path
        primary = Path(target) if target else search_paths[0]
        try:
            return Path(os.path.relpath(primary, cwd))
        except Exception:
            return primary.resolve()

    def load(self, model_path: Optional[str] = None, force_reload: bool = False) -> YOLO:
        """Load the YOLO model from disk and perform warmup inference."""
        with self._model_lock:
            if self._model is not None and not force_reload:
                return self._model

            resolved_path = self.resolve_model_path(model_path)
            if not resolved_path.exists():
                raise FileNotFoundError(
                    f"Model weights file not found at: {resolved_path}. "
                    f"Please verify settings.MODEL_PATH or place weights in ml/weights/best.pt"
                )

            logger.info("Loading MarineScan YOLO model from %s on device %s...", resolved_path, self._device)
            start_time = time.perf_counter()

            model = YOLO(str(resolved_path))
            
            # Send model to target device if supported
            try:
                model.to(self._device)
            except Exception as e:
                logger.warning("Could not transfer model directly to device %s (%s), falling back to default.", self._device, e)

            # Warmup inference to eliminate cold-start latency on first user request
            self._warmup(model)

            self._load_duration_ms = (time.perf_counter() - start_time) * 1000.0
            self._model = model
            self._model_path = resolved_path
            self._is_loaded = True

            logger.info(
                "Model loaded successfully in %.2f ms (Classes: %s)",
                self._load_duration_ms,
                getattr(model, "names", CLASS_NAMES),
            )
            return self._model

    def _warmup(self, model: YOLO) -> None:
        """Run a single inference pass on synthetic black canvas to warmup model layers."""
        try:
            dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
            model.predict(
                source=dummy_frame,
                device=self._device,
                conf=0.25,
                verbose=False,
            )
            logger.debug("Model warmup completed successfully.")
        except Exception as err:
            logger.warning("Model warmup failed (non-critical): %s", err)

    def get_model(self) -> YOLO:
        """Retrieve the cached YOLO model, loading it if not yet in memory."""
        if self._model is None:
            return self.load()
        return self._model

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded and self._model is not None

    @property
    def device(self) -> str:
        return self._device

    def get_info(self) -> Dict[str, Any]:
        """Return diagnostic and configuration metadata for the loaded model."""
        path_str = str(self._model_path) if self._model_path else "unresolved"
        file_size_mb = (
            round(self._model_path.stat().st_size / (1024 * 1024), 2)
            if self._model_path and self._model_path.exists()
            else 0.0
        )
        names = getattr(self._model, "names", CLASS_NAMES) if self._model else CLASS_NAMES

        return {
            "is_loaded": self.is_loaded,
            "device": self._device,
            "weights_path": path_str,
            "weights_size_mb": file_size_mb,
            "classes": names,
            "total_classes": len(names),
            "task": getattr(self._model, "task", "detect") if self._model else "detect",
            "load_duration_ms": round(self._load_duration_ms, 2),
            "default_confidence_threshold": settings.CONFIDENCE_THRESHOLD,
        }


# Global singleton instance
model_loader = ModelLoader()


def get_model() -> YOLO:
    """Convenience function to access the active YOLO model."""
    return model_loader.get_model()


if __name__ == "__main__":
    import json
    print("\n" + "=" * 50)
    print("MarineScan Model Verification")
    print("=" * 50)
    print("Loading model and checking status...")
    model = model_loader.get_model()
    info = model_loader.get_info()
    print(f"Status:        {'READY' if info['is_loaded'] else 'FAILED'}")
    print(f"Compute Device: {info['device'].upper()}")
    print(f"Task:          {info['task']}")
    print(f"Weights Path:  {info['weights_path']}")
    print(f"Weights Size:  {info['weights_size_mb']} MB")
    print(f"Load Time:     {info['load_duration_ms']} ms")
    print(f"Total Classes: {info['total_classes']}")
    print("\nRegistered Classes:")
    for cid, cname in info["classes"].items():
        print(f"  [{cid}] {cname}")
    print("=" * 50 + "\n")
