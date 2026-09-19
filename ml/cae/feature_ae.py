"""Feature-reconstruction autoencoder (a CAE that works) + PatchCore ensemble, on SCTD.

A plain pixel CAE inverts on smooth sonar objects. This autoencoder instead reconstructs
DEEP FEATURES (ResNet18 layer2+layer3) of seabed. Objects deviate in feature space, so
their feature-reconstruction error is high -> no inversion. We also test the union
ensemble (feature-AE OR PatchCore fires).

Trains on SCTD seabed patch features, evaluates recall / FP / pixel-AUROC on SCTD test,
head-to-head with PatchCore on the identical images.

Usage: python -m ml.cae.feature_ae --data ../datasets/SCTD-master/SCTD10/SCTD
"""

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from ml.cae.patchcore import FeatureExtractor, PatchCore
from ml.cae.sctd import split_images, voc_boxes

RUN = Path("ml/cae/runs/feature_ae")


class FeatAE(nn.Module):
    """MLP autoencoder over 384-d L2-normalized feature vectors."""
    def __init__(self, d=384, latent=64):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(d, 256), nn.ReLU(True), nn.Linear(256, latent))
        self.dec = nn.Sequential(nn.Linear(latent, 256), nn.ReLU(True), nn.Linear(256, d))

    def forward(self, x):
        return F.normalize(self.dec(self.enc(x)), dim=1)


def auroc(pos, neg):
    a = np.concatenate([pos, neg]); r = a.argsort().argsort() + 1.0
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


class FeatAEScorer:
    def __init__(self, model, fe: FeatureExtractor, calib):
        self.model, self.fe, self.calib = model, fe, calib

    @torch.no_grad()
    def score_map(self, gray):
        h, w = gray.shape
        t = torch.from_numpy(gray.astype(np.float32) / 255.0)[None, None].to(self.fe.device)
        f = self.fe.features(t)                       # (1,384,fh,fw)
        _, c, fh, fw = f.shape
        v = f[0].permute(1, 2, 0).reshape(-1, c)
        err = ((self.model(v) - v) ** 2).mean(dim=1).reshape(fh, fw).cpu().numpy()
        return cv2.resize(err, (w, h), interpolation=cv2.INTER_CUBIC)


def per_image_counts(score_fn, thr, test, ann, min_area=300):
    """Per-image (n_boxes, n_hits, n_fp) so we can bootstrap over images."""
    rows = []
    for p in test:
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is None or min(g.shape) < 32:
            continue
        e = cv2.GaussianBlur(score_fn(g), (0, 0), 3)
        boxes = voc_boxes(ann / (p.stem + ".xml"))
        m = cv2.morphologyEx((e > thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        nlab, _, stats, _ = cv2.connectedComponentsWithStats(m)
        dets = [stats[k] for k in range(1, nlab) if stats[k][4] >= min_area]
        hits = sum(any(not (dx + dw < x0 or dx > x1 or dy + dh < y0 or dy > y1) for dx, dy, dw, dh, _ in dets)
                   for x0, y0, x1, y1 in boxes)
        fp = sum(not any(not (dx + dw < x0 or dx > x1 or dy + dh < y0 or dy > y1) for x0, y0, x1, y1 in boxes)
                 for dx, dy, dw, dh, _ in dets)
        rows.append((len(boxes), hits, fp))
    return rows


def detect_metrics(score_fn, thr, test, ann, min_area=300):
    rows = per_image_counts(score_fn, thr, test, ann, min_area)
    nb = sum(r[0] for r in rows); hit = sum(r[1] for r in rows); fp = sum(r[2] for r in rows)
    return hit / max(nb, 1), fp / max(len(rows), 1)


def bootstrap_fp(rows_fae, rows_pc, iters=2000, seed=0):
    """Bootstrap over images: 95% CI on FP/image for each method and on their difference."""
    rng = np.random.RandomState(seed)
    n = len(rows_fae)
    fae_fp = np.array([r[2] for r in rows_fae], float)
    pc_fp = np.array([r[2] for r in rows_pc], float)
    fae_hit = np.array([r[1] for r in rows_fae]); pc_hit = np.array([r[1] for r in rows_pc])
    nb = np.array([r[0] for r in rows_fae])
    d_fae, d_pc, d_diff, r_fae, r_pc = [], [], [], [], []
    for _ in range(iters):
        idx = rng.randint(0, n, n)
        d_fae.append(fae_fp[idx].mean()); d_pc.append(pc_fp[idx].mean())
        d_diff.append(pc_fp[idx].mean() - fae_fp[idx].mean())
        r_fae.append(fae_hit[idx].sum() / max(nb[idx].sum(), 1))
        r_pc.append(pc_hit[idx].sum() / max(nb[idx].sum(), 1))
    q = lambda v: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5)))
    return {"fae_fp": q(d_fae), "pc_fp": q(d_pc), "diff_pc_minus_fae": q(d_diff),
            "fae_recall": q(r_fae), "pc_recall": q(r_pc)}


def pixel_auroc(score_fn, test, ann):
    pos, neg = [], []
    for p in test:
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is None or min(g.shape) < 32:
            continue
        e = cv2.GaussianBlur(score_fn(g), (0, 0), 3)
        gt = np.zeros(g.shape, bool)
        for x0, y0, x1, y1 in voc_boxes(ann / (p.stem + ".xml")):
            gt[max(y0, 0):y1, max(x0, 0):x1] = True
        if gt.any():
            pos.append(e[gt][::5]); neg.append(e[~gt][::19])
    return auroc(np.concatenate(pos), np.concatenate(neg))


def percentiles(vals):
    return {k: float(np.percentile(vals, q)) for k, q in (("p95", 95), ("p99", 99), ("p999", 99.9))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=40)
    a = ap.parse_args()
    RUN.mkdir(parents=True, exist_ok=True)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    fe = FeatureExtractor(dev)
    ann = a.data / "Annotations"
    _, _, test = split_images(a.data)

    # ---- train feature-AE on SCTD seabed features ----
    z = np.load("ml/cae/runs/pc_sctd/patches.npz")
    ftr = fe.patch_locations(z["train"])
    fva = fe.patch_locations(z["val"])
    if len(ftr) > 60000:
        ftr = ftr[np.random.RandomState(0).choice(len(ftr), 60000, replace=False)]
    x = torch.from_numpy(ftr).to(dev)
    model = FeatAE().to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    print(f"training feature-AE on {len(x)} seabed feature vectors...")
    for ep in range(a.epochs):
        perm = torch.randperm(len(x))
        tot = 0.0
        for i in range(0, len(x), 512):
            b = x[perm[i:i + 512]]
            loss = F.mse_loss(model(b), b)
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(b)
        if ep % 10 == 0 or ep == a.epochs - 1:
            print(f"  epoch {ep:2d} feat-mse={tot / len(x):.6f}")
    model.eval()

    # calibrate feature-AE on val seabed
    with torch.no_grad():
        ve = ((model(torch.from_numpy(fva).to(dev)) - torch.from_numpy(fva).to(dev)) ** 2).mean(1).cpu().numpy()
    fae = FeatAEScorer(model, fe, percentiles(ve))
    torch.save({"state": model.state_dict(), "d": 384, "latent": 64, "calib": fae.calib},
               RUN / "featae.pt")
    print("saved feature-AE ->", RUN / "featae.pt", "calib:", fae.calib)
    pc = PatchCore(Path("ml/cae/runs/pc_combined"))

    # ---- ensemble: normalize each score by its own p99, take the max ----
    def ens_score(g):
        a1 = cv2.GaussianBlur(fae.score_map(g), (0, 0), 3) / (fae.calib["p99"] + 1e-9)
        a2 = cv2.GaussianBlur(pc.score_map(g), (0, 0), 3) / (pc.calib["p99"] + 1e-9)
        return np.maximum(a1, a2)

    print("\n=== SCTD test: feature-AE vs PatchCore vs ensemble ===")
    rows = []
    for name, scorer, thr in [
        ("Feature-AE", fae.score_map, fae.calib["p95"]),
        ("PatchCore", pc.score_map, pc.calib["p95"]),
        ("Ensemble (max)", ens_score, 1.0),  # normalized units; p95 -> ~ threshold 1.0
    ]:
        rec, fp = detect_metrics(scorer, thr, test, ann)
        au = pixel_auroc(scorer, test, ann)
        rows.append((name, rec, fp, au))
        print(f"{name:16s} recall@p95={rec:6.1%}  FP/img={fp:5.2f}  pixelAUROC={au:.3f}")
    (RUN / "results.txt").write_text(
        "method,recall_p95,fp_per_image,pixel_auroc\n" +
        "\n".join(f"{n},{r:.4f},{f:.4f},{a:.4f}" for n, r, f, a in rows))

    # ---- bootstrap confirmation of the FP advantage (2000 resamples over images) ----
    print("\n=== bootstrap (2000 resamples over images), 95% CI ===")
    rows_fae = per_image_counts(fae.score_map, fae.calib["p95"], test, ann)
    rows_pc = per_image_counts(pc.score_map, pc.calib["p95"], test, ann)
    ci = bootstrap_fp(rows_fae, rows_pc)
    print(f"Feature-AE FP/img: {ci['fae_fp'][0]:.2f}-{ci['fae_fp'][1]:.2f}   recall {ci['fae_recall'][0]:.1%}-{ci['fae_recall'][1]:.1%}")
    print(f"PatchCore  FP/img: {ci['pc_fp'][0]:.2f}-{ci['pc_fp'][1]:.2f}   recall {ci['pc_recall'][0]:.1%}-{ci['pc_recall'][1]:.1%}")
    lo, hi = ci["diff_pc_minus_fae"]
    verdict = "CONFIRMED (CI excludes 0)" if lo > 0 else "NOT confirmed (CI includes 0)"
    print(f"FP reduction (PatchCore - Feature-AE): {lo:.2f} to {hi:.2f} per image -> {verdict}")
    import json
    (RUN / "bootstrap.json").write_text(json.dumps(ci, indent=2))
    print("wrote", RUN / "results.txt", "and bootstrap.json")


if __name__ == "__main__":
    main()
