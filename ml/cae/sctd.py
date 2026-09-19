"""SCTD (Pascal VOC) box-based benchmark for PatchCore.

Real bounding boxes let us measure properly (no center/border proxy):
  prepare : split images, harvest seabed patches from TRAIN images (excluding real boxes) -> npz
  eval    : on TEST images, pixel AUROC (inside-box vs outside-box seabed) + detection recall/FP

Usage:
  python -m ml.cae.sctd prepare --data ../datasets/SCTD-master/SCTD10/SCTD --out ml/cae/runs/pc_sctd
  python -m ml.cae.sctd eval    --data ../datasets/SCTD-master/SCTD10/SCTD --bank ml/cae/runs/pc_sctd
"""

import argparse
import random
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np


def voc_boxes(xml_path: Path):
    if not xml_path.exists():
        return []
    r = ET.parse(xml_path).getroot()
    out = []
    for o in r.findall("object"):
        b = o.find("bndbox")
        out.append((int(float(b.findtext("xmin"))), int(float(b.findtext("ymin"))),
                    int(float(b.findtext("xmax"))), int(float(b.findtext("ymax")))))
    return out


def split_images(data: Path, seed=0):
    imgs = sorted((data / "JPEGImages").glob("*.jpg"))
    random.Random(seed).shuffle(imgs)
    n = len(imgs)
    tr = imgs[:int(0.7 * n)]
    va = imgs[int(0.7 * n):int(0.85 * n)]
    te = imgs[int(0.85 * n):]
    return tr, va, te


def _overlaps(x, y, s, boxes, margin):
    for x0, y0, x1, y1 in boxes:
        if x < x1 + margin and x + s > x0 - margin and y < y1 + margin and y + s > y0 - margin:
            return True
    return False


def harvest(g, boxes, size, stride, margin, min_std, max_dark):
    h, w = g.shape
    out = []
    for y in range(0, h - size + 1, stride):
        for x in range(0, w - size + 1, stride):
            if _overlaps(x, y, size, boxes, margin):
                continue
            p = g[y:y + size, x:x + size]
            if p.std() < min_std or (p < 8).mean() > max_dark:
                continue
            out.append(p)
    return out


def cmd_prepare(a):
    tr, va, te = split_images(a.data)
    ann = a.data / "Annotations"
    rng = random.Random(0)
    data = {"train": [], "val": []}
    for split, files in (("train", tr), ("val", va)):
        for p in files:
            g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if g is None or min(g.shape) < a.patch:
                continue
            boxes = voc_boxes(ann / (p.stem + ".xml"))
            ps = harvest(g, boxes, a.patch, a.stride, a.margin, a.min_std, a.max_dark)
            rng.shuffle(ps)
            data[split].extend(ps[:a.max_per_image])
    a.out.mkdir(parents=True, exist_ok=True)
    arr = {k: (np.stack(v).astype(np.uint8) if v else np.zeros((0, a.patch, a.patch), np.uint8))
           for k, v in data.items()}
    arr["test"] = np.zeros((0, a.patch, a.patch), np.uint8)
    np.savez_compressed(a.out / "patches.npz", **arr)
    print({k: len(v) for k, v in arr.items()}, "-> build bank next")


def _auroc(pos, neg):
    a = np.concatenate([pos, neg]); r = a.argsort().argsort() + 1
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def cmd_eval(a):
    from ml.cae.patchcore import PatchCore
    pc = PatchCore(a.bank)
    _, _, te = split_images(a.data)
    ann = a.data / "Annotations"
    out = Path(a.bank) / "sctd_diag"; out.mkdir(exist_ok=True)
    pos, neg = [], []
    hit, nb, fp, nimg = 0, 0, 0, 0
    # detection threshold from seabed calibration
    thr = pc.calib[a.thr_key]
    for i, p in enumerate(te):
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is None or min(g.shape) < 32:
            continue
        nimg += 1
        h, w = g.shape
        boxes = voc_boxes(ann / (p.stem + ".xml"))
        e = cv2.GaussianBlur(pc.score_map(g), (0, 0), 3)
        gt = np.zeros((h, w), bool)
        for x0, y0, x1, y1 in boxes:
            gt[max(y0, 0):y1, max(x0, 0):x1] = True
        if gt.any():
            pos.append(e[gt][::5]); neg.append(e[~gt][::19])
        # detection: threshold -> connected components
        m = cv2.morphologyEx((e > thr).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        nlab, _, stats, _ = cv2.connectedComponentsWithStats(m)
        dets = [stats[k] for k in range(1, nlab) if stats[k][4] >= a.min_area]
        for x0, y0, x1, y1 in boxes:
            nb += 1
            hit += any(not (dx + dw < x0 or dx > x1 or dy + dh < y0 or dy > y1)
                       for dx, dy, dw, dh, _ in dets)
        for dx, dy, dw, dh, _ in dets:
            if not any(not (dx + dw < x0 or dx > x1 or dy + dh < y0 or dy > y1)
                       for x0, y0, x1, y1 in boxes):
                fp += 1
        if i < a.overlays:
            heat = cv2.applyColorMap((np.clip(e / (e.max() + 1e-6), 0, 1) * 255).astype(np.uint8), cv2.COLORMAP_JET)
            vis = cv2.addWeighted(cv2.cvtColor(g, cv2.COLOR_GRAY2BGR), 0.5, heat, 0.5, 0)
            for x0, y0, x1, y1 in boxes:
                cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2.imwrite(str(out / f"{p.stem}.jpg"), vis)
    pos, neg = np.concatenate(pos), np.concatenate(neg)
    print(f"test images: {nimg}  boxes: {nb}")
    print(f"pixel AUROC (box vs seabed): {_auroc(pos, neg):.3f}")
    print(f"mean score  box={pos.mean():.4f} seabed={neg.mean():.4f} ratio={pos.mean()/neg.mean():.2f}x")
    print(f"detection recall @p99: {hit}/{nb} = {hit/max(nb,1):.1%}   false pos/image: {fp/max(nimg,1):.2f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--patch", type=int, default=64)
    p.add_argument("--stride", type=int, default=24)
    p.add_argument("--margin", type=int, default=24)
    p.add_argument("--min-std", type=float, default=6.0)
    p.add_argument("--max-dark", type=float, default=0.3)
    p.add_argument("--max-per-image", type=int, default=120)
    p.set_defaults(func=cmd_prepare)
    e = sub.add_parser("eval")
    e.add_argument("--data", type=Path, required=True)
    e.add_argument("--bank", type=Path, required=True)
    e.add_argument("--min-area", type=int, default=300)
    e.add_argument("--thr-key", default="p99", choices=["p95", "p99", "p999"])
    e.add_argument("--overlays", type=int, default=10)
    e.set_defaults(func=cmd_eval)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
