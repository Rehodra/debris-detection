# Handoff — Open-Set Anomaly Branch (Branch 2)

This document hands off the work that replaced the reconstruction-CAE anomaly branch
with a **PatchCore feature-space detector**, and wired it into the backend pipeline.

---

## 1. TL;DR

- **Old plan:** a Convolutional Autoencoder (CAE) that flags targets by reconstruction error.
- **Problem:** on sonar, man-made objects (wrecks, aircraft, pipes) are *smoother* than the
  grainy seabed, so the CAE reconstructs the object **better** than the background — the anomaly
  signal **inverts**. Measured: CAE caught only **50%** of targets on SCTD, and scored **below
  chance** (AUROC ~0.46) on object-centric KLSG data.
- **Fix:** **PatchCore** — compare each image location's deep features to a memory bank of
  *normal seabed* features; anything far from seabed scores high. No inversion.
- **Result (SCTD, real boxes):** **100% detection recall** vs 50% for the CAE, at ~3.3 false
  positives/image (filtered downstream by shadow + physics + fusion).
- **Integration:** drops into the existing pipeline as Branch 2 with the same candidate shape
  and a `P_CAE` score; **no backend logic rewritten.**

---

## 2. Why not the CAE (the core insight)

A reconstruction autoencoder learns to redraw normal seabed and flags whatever it redraws badly.
But a target in side-scan sonar is a **smooth bright highlight + a clean dark shadow**, while
seabed is **high-frequency speckle**. The autoencoder finds the smooth object *easy* to redraw
(low error) and the speckled seabed *hard* (high error), so the target hides in the low-error
region. This is a known failure mode (reconstruction error is not a reliable anomaly proxy) and
here it is severe enough to invert the signal.

## 3. What we use instead: PatchCore

1. A frozen ImageNet **ResNet18** turns image patches into feature vectors (layer2+layer3,
   L2-normalized, aggregated over a 3x3 neighborhood).
2. Offline, we build a **coreset memory bank** of features from *seabed-only* patches
   (harvested by excluding labelled target boxes).
3. At inference, each location's feature is compared to the bank; **cosine distance to the
   nearest normal feature = anomaly score**. High distance -> candidate box + `P_CAE`.

A smooth object is still *far* from seabed in feature space, so it no longer hides.

## 4. Evidence (see `ml/cae/runs/evidence/`)

Benchmark: **SCTD**, 54 held-out test images, 56 boxes, 1000-sample bootstrap.

| Method | Detection recall @p95 | FP/image @p95 | Pixel AUROC (95% CI) |
|---|---|---|---|
| CAE (reconstruction) | 50.0% | 0.57 | 0.664 (0.61–0.72) |
| **PatchCore (SCTD+KLSG)** | **100%** | 3.26 | 0.666 (0.61–0.71) |

- **Detection recall is the operational metric** — PatchCore catches every target, the CAE half.
- **Honest note:** on the diluted *pixel* AUROC metric the two are statistically tied (overlapping
  CIs). The separation is real at the detection level and on object-centric data (KLSG), where the
  CAE inverts. This is stated openly in `EVIDENCE.md`.
- Artifacts: `EVIDENCE.md`, `roc.png`, `pr.png`, `evidence.json`.

## 5. Backend integration (Branch 2)

| File | Role |
|---|---|
| `backend/app/ml/anomaly/patchcore.py` | Inference detector: `score_map()` + `detect()` (emits candidate dicts, class 5) |
| `backend/app/ml/anomaly/resnet.py` | Pure-torch ResNet18 (torchvision native ops fail on Windows; weights loaded by file/URL) |
| `backend/app/ml/anomaly/seabed_bank.npz` | Trained seabed memory bank (committed) |
| `backend/app/services/anomaly_service.py` | Lazy singleton `anomaly_service`; graceful disable if torch/bank missing |
| `backend/app/core/config.py` | `ANOMALY_ENABLED`, `ANOMALY_BANK_PATH`, `ANOMALY_THRESHOLD_KEY` (p95/p99/p999), `ANOMALY_MIN_AREA` |
| `backend/app/services/master_pipeline_service.py` | Stage 5 merges anomaly candidates with YOLO (IoU dedup) |

Flow: anomaly candidates carry `confidence = p_cae`, so they ride the existing
shadow -> physics -> confidence-fusion path unchanged (the diagram's `alpha*(P_YOLO or P_CAE)` term).

### ImageNet weights (offline)
`resnet.py` loads `resnet18-imagenet.pth` if present, else downloads from torch.hub. The 45 MB
weight file is **not committed** (it is standard, freely downloadable). For an air-gapped deploy,
drop `resnet18-imagenet.pth` into `backend/app/ml/anomaly/` (or add it via Git LFS). If missing and
offline, the branch disables gracefully and the rest of the pipeline is unaffected.

## 6. Reproduce / retrain (offline research code in `ml/cae/`)

```bash
# from repo root, with a venv that has torch + opencv-python-headless + numpy (+ matplotlib for evidence)
export PYTHONPATH=.
# 1) harvest seabed patches (excludes VOC boxes) and build the bank
python -m ml.cae.sctd prepare --data ../datasets/SCTD-master/SCTD10/SCTD --out ml/cae/runs/pc_sctd
python -m ml.cae.patchcore    --patches ml/cae/runs/pc_sctd/patches.npz  --out ml/cae/runs/pc_sctd
# 2) evaluate on held-out test images (real boxes)
python -m ml.cae.sctd eval    --data ../datasets/SCTD-master/SCTD10/SCTD --bank ml/cae/runs/pc_sctd
# 3) full evidence package (CAE baseline vs PatchCore, ROC/PR, bootstrap CIs)
python -m ml.cae.evidence     --data ../datasets/SCTD-master/SCTD10/SCTD
```

`ml/cae/README.md` has the module map. Datasets live outside the repo (`../datasets/…`).

## 7. Known limits / next steps
- SCTD test set is small (54 images) -> wide confidence intervals. A larger labelled set would tighten them.
- Backbone is ResNet18; WideResNet50 (PatchCore's default) may improve accuracy further.
- Threshold `ANOMALY_THRESHOLD_KEY` trades recall vs false positives: `p95` (100% recall) … `p999` (fewest FP).
- The 45 MB ImageNet `.pth` should move to Git LFS if offline deployment is a hard requirement.

## 8. Naming note
The branch is still labelled "CAE" / `P_CAE` in code and the architecture diagram for
compatibility. The *method* underneath is PatchCore, not an autoencoder.
