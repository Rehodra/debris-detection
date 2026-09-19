"""Feature-reconstruction autoencoder detector for the open-set branch (inference only).

A real autoencoder, but it reconstructs DEEP FEATURES (ResNet18 layer2+layer3) of seabed
rather than pixels. Man-made objects deviate in feature space, so their feature-reconstruction
error is high -> no inversion (the failure mode of a pixel CAE). On SCTD it matches PatchCore's
recall with fewer false positives, and needs no memory bank (just a small MLP + the backbone).
"""

from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from app.ml.anomaly.patchcore import _FeatureExtractor


class _FeatAE(nn.Module):
    """MLP autoencoder over 384-d L2-normalized feature vectors."""
    def __init__(self, d: int = 384, latent: int = 64):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(d, 256), nn.ReLU(True), nn.Linear(256, latent))
        self.dec = nn.Sequential(nn.Linear(latent, 256), nn.ReLU(True), nn.Linear(256, d))

    def forward(self, x):
        return F.normalize(self.dec(self.enc(x)), dim=1)


class FeatureAEDetector:
    """Loads the trained feature-AE and turns an image into anomaly candidate boxes."""

    def __init__(self, ckpt_path: Path, device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fe = _FeatureExtractor(self.device)
        ck = torch.load(ckpt_path, map_location=self.device)
        self.model = _FeatAE(ck.get("d", 384), ck.get("latent", 64)).to(self.device).eval()
        self.model.load_state_dict(ck["state"])
        self.calib = ck["calib"]

    @torch.no_grad()
    def score_map(self, gray: np.ndarray) -> np.ndarray:
        """Per-pixel anomaly score = feature-reconstruction error."""
        h, w = gray.shape
        t = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None].to(self.device)
        f = self.fe.features(t)
        _, c, fh, fw = f.shape
        v = f[0].permute(1, 2, 0).reshape(-1, c)
        err = ((self.model(v) - v) ** 2).mean(dim=1).reshape(fh, fw).cpu().numpy()
        return cv2.resize(err, (w, h), interpolation=cv2.INTER_CUBIC)

    def detect(self, image_bgr: np.ndarray, thr_key: str = "p95", thr_scale: float = 1.0,
               min_area: int = 300) -> List[Dict]:
        """Open-set anomaly candidates (class 5 / 'other') in the pipeline dict shape."""
        from app.ml.class_map import get_class_metadata
        meta = get_class_metadata(5)
        gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        emap = cv2.GaussianBlur(self.score_map(gray), (0, 0), 3)
        thr = self.calib.get(thr_key, self.calib["p95"]) * thr_scale
        mask = cv2.morphologyEx((emap > thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        h, w = gray.shape
        out = []
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if area < min_area:
                continue
            peak = float(emap[y:y + bh, x:x + bw].max())
            p_cae = min(1.0, float(1.0 - 0.5 * np.exp(-(peak / thr - 1.0) * 2.0))) if peak >= thr else 0.5
            out.append({
                "detection_id": f"cae-{i}",
                "class_id": 5, "class_name": meta.name, "display_name": meta.display_name,
                "category": meta.category, "risk_level": meta.risk_level,
                "color_hex": meta.color_hex, "color_rgb": list(meta.color_rgb),
                "confidence": p_cae, "p_cae": p_cae, "source": "cae",
                "bbox": {
                    "x_min": float(x), "y_min": float(y), "x_max": float(x + bw), "y_max": float(y + bh),
                    "width": float(bw), "height": float(bh),
                    "normalized_x_min": float(x / w), "normalized_y_min": float(y / h),
                    "normalized_x_max": float((x + bw) / w), "normalized_y_max": float((y + bh) / h),
                },
                "area_pixels": float(bw * bh),
                "physical_dimensions": None,
            })
        return out
