"""Minimal reconstruction-CAE baseline (for the evidence package only).

Trains on SCTD seabed patches and scores anomalies by MSE reconstruction error, so it
can be compared head-to-head with PatchCore on the same SCTD test set. This is the
approach we rejected; it is kept here purely as the documented baseline.
"""

from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class _CAE(nn.Module):
    def __init__(self, patch=64, latent=128):
        super().__init__()
        self.enc = nn.Sequential(
            nn.Conv2d(1, 32, 4, 2, 1), nn.ReLU(True),      # 32
            nn.Conv2d(32, 64, 4, 2, 1), nn.ReLU(True),     # 16
            nn.Conv2d(64, 128, 4, 2, 1), nn.ReLU(True),    # 8
            nn.Conv2d(128, 128, 4, 2, 1), nn.ReLU(True),   # 4
        )
        self.fc1 = nn.Linear(128 * (patch // 16) ** 2, latent)
        self.fc2 = nn.Linear(latent, 128 * (patch // 16) ** 2)
        self.dec = nn.Sequential(
            nn.ConvTranspose2d(128, 128, 4, 2, 1), nn.ReLU(True),
            nn.ConvTranspose2d(128, 64, 4, 2, 1), nn.ReLU(True),
            nn.ConvTranspose2d(64, 32, 4, 2, 1), nn.ReLU(True),
            nn.ConvTranspose2d(32, 1, 4, 2, 1), nn.Sigmoid(),
        )
        self.patch = patch

    def forward(self, x):
        z = self.enc(x)
        b, c, h, w = z.shape
        z = self.fc2(self.fc1(z.flatten(1))).view(b, c, h, w)
        return self.dec(z)


def train_cae(patches_npz: Path, out_pt: Path, patch=64, epochs=25, bs=128, lr=1e-3):
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tr = np.load(patches_npz)["train"].astype(np.float32) / 255.0
    x = torch.from_numpy(tr)[:, None]
    model = _CAE(patch).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    n = len(x)
    for ep in range(epochs):
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, bs):
            b = x[perm[i:i + bs]].to(dev)
            rec = model(b)
            loss = F.mse_loss(rec, b)
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(b)
        if ep % 5 == 0 or ep == epochs - 1:
            print(f"  cae epoch {ep:2d} mse={tot / n:.5f}")
    out_pt.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state": model.state_dict(), "patch": patch}, out_pt)
    return out_pt


class CAEScorer:
    def __init__(self, ckpt: Path):
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        ck = torch.load(ckpt, map_location=self.dev)
        self.patch = ck["patch"]
        self.model = _CAE(self.patch).to(self.dev).eval()
        self.model.load_state_dict(ck["state"])

    @torch.no_grad()
    def score_map(self, gray: np.ndarray) -> np.ndarray:
        p, stride = self.patch, self.patch // 2
        h, w = gray.shape
        g = np.pad(gray, ((0, max(0, p - h)), (0, max(0, p - w))), mode="reflect")
        H, W = g.shape
        acc = np.zeros((H, W), np.float32); cnt = np.zeros((H, W), np.float32)
        ys = sorted(set(list(range(0, H - p + 1, stride)) + [H - p]))
        xs = sorted(set(list(range(0, W - p + 1, stride)) + [W - p]))
        tiles = [(y, x) for y in ys for x in xs]
        for i in range(0, len(tiles), 64):
            ch = tiles[i:i + 64]
            b = np.stack([g[y:y + p, x:x + p] for y, x in ch]).astype(np.float32) / 255.0
            t = torch.from_numpy(b)[:, None].to(self.dev)
            e = ((self.model(t) - t) ** 2)[:, 0].cpu().numpy()
            for (y, x), em in zip(ch, e):
                acc[y:y + p, x:x + p] += em; cnt[y:y + p, x:x + p] += 1
        return (acc / np.maximum(cnt, 1))[:h, :w]
