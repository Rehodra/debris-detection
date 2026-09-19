"""PatchCore feature-space anomaly detector (inference only) for the open-set branch.

Compares deep ResNet18 features of each image location to a coreset memory bank of
NORMAL seabed features; high feature distance = anomaly. Unlike a reconstruction
autoencoder (whose error inverts on smooth man-made objects), this reliably scores
shipwrecks / aircraft / pipes and their acoustic shadows above the seabed.

The bank + calibration are produced offline (see ml/cae) and shipped as an .npz.
"""

from pathlib import Path
from typing import Dict, List, Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F

from app.ml.anomaly.resnet import resnet18_pretrained

_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


class _FeatureExtractor:
    def __init__(self, device):
        self.device = device
        net = resnet18_pretrained(device)
        for p in net.parameters():
            p.requires_grad_(False)
        self.stem = torch.nn.Sequential(net.conv1, net.bn1, net.relu, net.maxpool)
        self.l1, self.l2, self.l3 = net.layer1, net.layer2, net.layer3
        self.mean, self.std = _MEAN.to(device), _STD.to(device)

    @torch.no_grad()
    def features(self, x1: torch.Tensor) -> torch.Tensor:
        """(B,1,H,W) in [0,1] -> (B,384,H/8,W/8), L2-normalized per location.

        Each location is aggregated with its 3x3 neighborhood (PatchCore's locally-aware
        features) so isolated speckle no longer fires as a false positive. Must stay in
        sync with the offline bank build (ml/cae/patchcore.py)."""
        x = (x1.repeat(1, 3, 1, 1) - self.mean) / self.std
        x = self.stem(x)
        a = self.l2(self.l1(x))
        b = self.l3(a)
        b = F.interpolate(b, size=a.shape[-2:], mode="bilinear", align_corners=False)
        f = F.avg_pool2d(torch.cat([a, b], dim=1), kernel_size=3, stride=1, padding=1)
        return F.normalize(f, dim=1)


class PatchCoreDetector:
    """Loads a seabed memory bank and turns an image into anomaly candidate boxes."""

    def __init__(self, bank_path: Path, device: Optional[str] = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fe = _FeatureExtractor(self.device)
        z = np.load(bank_path)
        self.bank = torch.from_numpy(z["bank"]).to(self.device)
        self.calib = {k: float(z[k]) for k in ("p95", "p99", "p999", "mean")}

    @torch.no_grad()
    def score_map(self, gray: np.ndarray) -> np.ndarray:
        """Per-pixel anomaly score (cosine distance to nearest normal-seabed feature)."""
        h, w = gray.shape
        t = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None].to(self.device)
        f = self.fe.features(t)
        _, c, fh, fw = f.shape
        v = f[0].permute(1, 2, 0).reshape(-1, c)
        d = (1.0 - (v @ self.bank.t()).max(dim=1).values).reshape(fh, fw).cpu().numpy()
        return cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)

    def detect(self, image_bgr: np.ndarray, thr_key: str = "p99", thr_scale: float = 1.0,
               min_area: int = 300) -> List[Dict]:
        """Return open-set anomaly candidates (class 5 / 'other') in the pipeline dict shape."""
        from app.ml.class_map import get_class_metadata
        meta = get_class_metadata(5)
        gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        emap = cv2.GaussianBlur(self.score_map(gray), (0, 0), 3)
        thr = self.calib.get(thr_key, self.calib["p99"]) * thr_scale
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
