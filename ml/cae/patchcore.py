"""PatchCore-style feature-space anomaly detector for side-scan seabed.

Unlike a reconstruction CAE (whose error inverts on smooth man-made objects), this
compares deep ImageNet features of each location to a coreset memory bank of NORMAL
seabed features. Anything whose features are far from seabed -- including smooth
highlights and shadows -- scores high. No target labels used; bank is seabed-only.

Backbone: ResNet18 (layer2+layer3), frozen. Features L2-normalized and concatenated.

`PatchCore.score_map()` produces a per-pixel anomaly map for the detector; this module's
CLI builds the seabed memory bank from a patches.npz. Evaluation lives in ml/cae/sctd.py.

Usage (build the bank):
  python -m ml.cae.patchcore --patches ml/cae/runs/pc_sctd/patches.npz --out ml/cae/runs/pc_sctd
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

_MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
_STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


class FeatureExtractor:
    """Frozen ResNet18; returns concatenated layer2+layer3 feature map (B, C, h, w)."""

    def __init__(self, device):
        from ml.cae.resnet import resnet18_pretrained
        self.device = device
        net = resnet18_pretrained(device)
        for p in net.parameters():
            p.requires_grad_(False)
        self.stem = torch.nn.Sequential(net.conv1, net.bn1, net.relu, net.maxpool)
        self.l1, self.l2, self.l3 = net.layer1, net.layer2, net.layer3
        self.mean, self.std = _MEAN.to(device), _STD.to(device)

    @torch.no_grad()
    def features(self, x1: torch.Tensor) -> torch.Tensor:
        """x1: (B,1,H,W) in [0,1] -> (B, 384, H/8, W/8) L2-normalized per location.

        Each location is aggregated with its 3x3 neighborhood (PatchCore's locally-aware
        features): a spot's descriptor includes its surroundings, so the anomaly map is
        smoother and isolated speckle no longer fires as a false positive.
        """
        x = (x1.repeat(1, 3, 1, 1) - self.mean) / self.std
        x = self.stem(x)
        a = self.l2(self.l1(x))            # (B,128,H/8,W/8)
        b = self.l3(a)                     # (B,256,H/16,W/16)
        b = F.interpolate(b, size=a.shape[-2:], mode="bilinear", align_corners=False)
        f = torch.cat([a, b], dim=1)
        f = F.avg_pool2d(f, kernel_size=3, stride=1, padding=1)  # neighborhood aggregation
        return F.normalize(f, dim=1)

    @torch.no_grad()
    def patch_locations(self, patches_u8: np.ndarray, bs: int = 128, keep_per_patch: int = 8,
                        seed: int = 0) -> np.ndarray:
        """Per-LOCATION feature vectors (consistent with score_map). Randomly keeps a few
        locations per patch to bound memory."""
        rng = np.random.RandomState(seed)
        out = []
        for i in range(0, len(patches_u8), bs):
            t = torch.from_numpy(patches_u8[i:i + bs].astype(np.float32) / 255.0)[:, None].to(self.device)
            f = self.features(t)                        # (b,384,fh,fw)
            b, c, fh, fw = f.shape
            v = f.permute(0, 2, 3, 1).reshape(b, fh * fw, c)
            sel = rng.randint(0, fh * fw, size=(b, min(keep_per_patch, fh * fw)))
            for j in range(b):
                out.append(v[j, sel[j]].cpu().numpy())
        return np.concatenate(out)


def greedy_coreset(x: np.ndarray, n: int, seed: int = 0) -> np.ndarray:
    """k-center greedy coreset subsampling (indices)."""
    rng = np.random.RandomState(seed)
    n = min(n, len(x))
    idx = [rng.randint(len(x))]
    d = np.linalg.norm(x - x[idx[0]], axis=1)
    for _ in range(1, n):
        j = int(d.argmax())
        idx.append(j)
        d = np.minimum(d, np.linalg.norm(x - x[j], axis=1))
    return np.array(idx)


class PatchCore:
    def __init__(self, bank_dir: Path, device: str = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.fe = FeatureExtractor(self.device)
        z = np.load(Path(bank_dir) / "bank.npz")
        self.bank = torch.from_numpy(z["bank"]).to(self.device)   # (N, 384)
        self.calib = {k: float(z[k]) for k in ("p95", "p99", "p999", "mean")}

    @torch.no_grad()
    def _dist_to_bank(self, feats: torch.Tensor) -> torch.Tensor:
        """feats: (M,384) normalized -> (M,) min distance to bank (via cosine)."""
        sims = feats @ self.bank.t()               # (M, N) cosine sim (both normalized)
        return (1.0 - sims.max(dim=1).values)      # cosine distance to nearest normal

    @torch.no_grad()
    def score_map(self, gray: np.ndarray, out_hw=None) -> np.ndarray:
        h, w = gray.shape
        t = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None].to(self.device)
        f = self.fe.features(t)                     # (1,384,h/8,w/8)
        _, c, fh, fw = f.shape
        v = f[0].permute(1, 2, 0).reshape(-1, c)
        d = self._dist_to_bank(v).reshape(fh, fw).cpu().numpy()
        return cv2.resize(d, (out_hw or (w, h))[::-1] if out_hw else (w, h), interpolation=cv2.INTER_CUBIC)


def cmd_build(a):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    fe = FeatureExtractor(dev)
    z = np.load(a.patches)
    tr, va = z["train"], z["val"]
    print(f"extracting features: train={len(tr)} val={len(va)}")
    ftr = fe.patch_locations(tr)
    # random pre-subsample before greedy coreset (standard PatchCore speedup)
    if len(ftr) > a.presample:
        ftr = ftr[np.random.RandomState(0).choice(len(ftr), a.presample, replace=False)]
    idx = greedy_coreset(ftr, a.bank_size)
    bank = ftr[idx]
    # calibrate on val seabed: distance to bank
    fva = fe.patch_locations(va)
    bt = torch.from_numpy(bank).to(dev)
    fv = torch.from_numpy(fva).to(dev)
    d = (1.0 - (fv @ bt.t()).max(dim=1).values).cpu().numpy()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / "bank.npz", bank=bank.astype(np.float32),
                        p95=np.percentile(d, 95), p99=np.percentile(d, 99),
                        p999=np.percentile(d, 99.9), mean=d.mean())
    print(f"bank={len(bank)} calib p99={np.percentile(d, 99):.4f} mean={d.mean():.4f} -> {out}")


def main():
    ap = argparse.ArgumentParser(description="Build a seabed feature memory bank (see ml/cae/sctd.py for eval).")
    ap.add_argument("--patches", type=Path, required=True, help="npz with 'train'/'val' seabed patch arrays")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--bank-size", type=int, default=6000)
    ap.add_argument("--presample", type=int, default=50000)
    cmd_build(ap.parse_args())


if __name__ == "__main__":
    main()
