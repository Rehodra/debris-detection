# Evidence Package - Open-Set Anomaly Branch

Benchmark: **SCTD** (Sonar Common Target Detection), Pascal-VOC boxes.
Test set: **54 held-out images, 56 target boxes** (image-level split, seed 0).
Both methods evaluated on the *same* images. Bootstrap: 1000 resamples over images.

## 1. Headline - detection performance (the operational metric)

A candidate generator is judged on recall (don't miss targets) and false-positives/image
(work the downstream shadow/physics/fusion stages must filter). Same test set, both methods:

| Method | Recall @p95 | FP/img @p95 | Recall @p99 | FP/img @p99 |
|---|---|---|---|---|
| CAE (reconstruction) | 50.0% | 0.57 | 44.6% | 0.69 |
| **PatchCore (SCTD+KLSG)** | **100.0%** | **3.26** | **100.0%** | **5.17** |

## 2. Pixel-level separability (AUROC, object vs seabed, 95% CI)

| Method | AUROC (95% CI) |
|---|---|
| CAE (reconstruction) | 0.664 (0.608-0.722) |
| PatchCore (SCTD only) | 0.687 (0.631-0.739) |
| PatchCore (SCTD+KLSG) | 0.666 (0.614-0.714) |

Curves: `roc.png`, `pr.png`. Note: at the pixel level on SCTD the CIs overlap - the two
methods are close on this diluted metric (boxes contain seabed context). The separation
shows up at the detection level (section 1) and, most sharply, on object-centric data where
the CAE inverts (KLSG: CAE structural AUROC ~0.46, below chance).

## 3. Ablations

- **Bank source** (pixel AUROC): SCTD-only 0.687 vs SCTD+KLSG 0.666.
- **Neighborhood features** (detection FP @p95, 100% recall): without = 7.8, with = 3.7 per image.

## 4. Honest caveats
- Small test set (54 images) -> wide CIs. Detection recall/FP is the metric to trust; pixel AUROC is indicative only.
- Pixel AUROC is diluted (boxes include seabed context), so it understates the gap.
- The CAE's clearest failure is on object-centric imagery (KLSG), where reconstruction error
  inverts because man-made objects are smoother than seabed. PatchCore does not invert.
- Seabed negatives exclude labelled boxes only; unlabelled clutter counts against precision.
