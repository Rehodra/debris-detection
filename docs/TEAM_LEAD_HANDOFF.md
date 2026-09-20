# Team Lead Handoff — Sonar Fusion Pipeline, Updated Anomaly Branch

**Audience:** team lead / reviewer. **Scope:** what changed in Branch 2 (the open-set
anomaly detector), how the pipeline works end to end, the evidence, and how it's deployed.
**Diagram:** `docs/sonar-fusion-v2-architecture.html` (interactive; open in any browser).

---

## 1. One-paragraph summary

The pipeline detects seabed targets from side-scan sonar by combining a **supervised
YOLO11 detector** (known classes) with an **open-set anomaly branch** (unknown objects),
then corroborating every candidate with **acoustic shadow + physics** before a **confidence
fusion** gate decides verified / review / rejected. The change in this handoff is **Branch 2**:
the planned reconstruction **CAE was replaced by a PatchCore feature-space detector** because
the CAE's anomaly signal *inverted* on real sonar objects. The new branch reaches **100%
target recall** on the labelled SCTD benchmark and drops into the existing pipeline unchanged.

## 2. Why the change (the key technical reason)

A reconstruction autoencoder flags anomalies by how badly it *redraws* an image. In sonar,
man-made objects (wrecks, aircraft, pipes) are **smooth** (bright highlight + clean shadow)
while seabed is **grainy speckle**. The CAE found the smooth object *easy* to redraw and the
seabed *hard* — so the error ran **backwards**: objects looked "normal," seabed looked
"anomalous." Measured: the CAE caught only **50%** of targets, and scored **below chance**
on object-centric data.

**PatchCore** fixes this: it compares each image location's deep features to a memory bank of
*normal seabed* features. A smooth object is still **far** from seabed in feature space, so it
no longer hides. No inversion.

## 3. How the pipeline works (follow the diagram)

1. **Sonar Input** — raster (JPG/PNG) or raw (XTF/JSF).
2. **Preprocessing** — speckle suppression, gain normalisation (TVG/EGN), nadir handling.
3. **Dual-branch candidate generation (parallel):**
   - **Branch 1 — YOLO11:** supervised detector, 7 known classes → `P_YOLO`.
   - **Branch 2 — PatchCore anomaly (updated):** open-set detector for unknown objects → `P_CAE`.
   - **Candidate Merge:** unions both, de-duplicates overlaps (IoU).
4. **Shadow + Physics:** each candidate is corroborated by its acoustic shadow (`S_shadow`)
   and trigonometric geometry / height plausibility (`S_geometry`).
5. **Confidence Fusion:** `C_final = α·(P_YOLO or P_CAE) + β·S_shadow + γ·S_geometry`,
   with α = 0.50, β = 0.30, γ = 0.20.
6. **Decision Gate:** `C ≥ 0.75` → verified 3D target; `0.50–0.75` → operator review (HITL);
   `C < 0.50` → rejected (flat clutter).
7. **Geo Output:** WGS84 geolocation, GeoJSON, map/report, audit log.

The shadow + physics + fusion stages **filter the anomaly branch's false positives**, so the
branch only needs high recall — which it delivers.

## 4. Two selectable detectors (one config flag)

`ANOMALY_METHOD` chooses the Branch-2 engine; both emit the same candidate shape and `P_CAE`:

| Method | What it is | Notes |
|---|---|---|
| `patchcore` (**default**) | Feature memory bank (nearest-neighbour) | Validated default; needs a 10 MB seabed bank |
| `feature_ae` | Feature-reconstruction autoencoder | A *real* CAE (reconstructs features, not pixels, so no inversion); lighter (~1 MB, no bank) |

On SCTD the two are **statistically tied** (both 100% recall; false-positive difference CI
includes 0), so the choice is engineering preference, not accuracy.

## 5. Evidence (honest)

Benchmark: **SCTD**, 54 held-out test images, real bounding boxes, 1000-sample bootstrap.

| Method | Detection recall | Pixel AUROC (95% CI) |
|---|---|---|
| Reconstruction CAE (rejected) | 50% | 0.66 (0.61–0.72) |
| **PatchCore / Feature-AE** | **100%** | 0.66–0.69 |

- **Detection recall is the number that matters** for a candidate generator; PatchCore catches
  every target, the CAE half.
- **Honest caveat:** on the *pixel* AUROC metric the CAEs and PatchCore look tied (small test
  set, diluted metric). The real, decisive gap is at the detection level and on object-centric
  data where the CAE inverts.
- **Cross-verification:** PatchCore and the feature-AE are two *independent* methods; they reach
  **100% target consensus (56/56)** — strong evidence the detections are real, not artifacts.
  (Ensembling them does not further cut false positives — tested.)
- Full report + plots: `ml/cae/runs/evidence/EVIDENCE.md`, `roc.png`, `pr.png`.

## 6. How it's deployed (backend)

- **`backend/app/services/master_pipeline_service.py`** — Stage 5 merges anomaly candidates
  with YOLO (one added line; nothing else in the pipeline changed).
- **`backend/app/services/anomaly_service.py`** — lazy singleton; picks the detector by
  `ANOMALY_METHOD`; **degrades gracefully** (if torch / weights are missing it disables and the
  rest of the pipeline is unaffected — the 83 existing tests are not at risk).
- **`backend/app/ml/anomaly/`** — detectors (`patchcore.py`, `feature_ae.py`), pure-torch
  ResNet18 backbone, and the trained weights (`seabed_bank.npz`, `featae.pt`).
- **Config:** `ANOMALY_ENABLED`, `ANOMALY_METHOD`, `ANOMALY_THRESHOLD_KEY` (p95/p99/p999 trades
  recall vs false positives), `ANOMALY_MIN_AREA`.
- **Offline:** the 45 MB ImageNet ResNet weights auto-download once via `torch.hub`, or are
  bundled for air-gapped deploys (see `HANDOFF_anomaly_branch.md`).

## 7. Status

- Delivered on branch **`feat/patchcore-anomaly-branch`** (commits `7a0b2e3`, `bd44323`).
- Technical detail: `HANDOFF_anomaly_branch.md`. Evidence: `ml/cae/runs/evidence/`.
- **Suggested next steps:** larger labelled test set to tighten confidence intervals; optional
  WideResNet50 backbone; wire `P_CAE`'s trust tier into the operator-review (HITL) UI.

## 8. Naming note

Code and diagram still label Branch 2 "CAE" / `P_CAE` for compatibility with the original
architecture. The *method* underneath is now PatchCore (or the feature-AE), not a pixel
autoencoder.
