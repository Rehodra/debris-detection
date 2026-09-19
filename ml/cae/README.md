# Open-set anomaly branch — PatchCore

Feature-space anomaly detection for the sonar-fusion pipeline's open-set branch.

**Why not a reconstruction autoencoder:** on real targets (shipwrecks, aircraft, pipes)
reconstruction error *inverts* — man-made objects are smoother (specular highlight +
uniform shadow) than speckled seabed, so an autoencoder reconstructs the object *better*
than the background and the anomaly hides in low error. PatchCore compares deep features
to a memory bank of normal seabed instead, which does not have this failure mode.

## Files
- `resnet.py` — pure-PyTorch ResNet18 with ImageNet weights loaded by URL
  (torchvision's native ops fail to load on this Windows box).
- `patchcore.py` — `FeatureExtractor` + `PatchCore` (score map / detect) + bank builder CLI.
- `sctd.py` — SCTD (Pascal VOC) benchmark: harvest seabed, then eval recall / FP / pixel AUROC.

## Run (from repo root, PYTHONPATH=.)
```
python -m ml.cae.sctd prepare --data ../datasets/SCTD-master/SCTD10/SCTD --out ml/cae/runs/pc_sctd
python -m ml.cae.patchcore    --patches ml/cae/runs/pc_sctd/patches.npz  --out ml/cae/runs/pc_sctd
python -m ml.cae.sctd eval    --data ../datasets/SCTD-master/SCTD10/SCTD --bank ml/cae/runs/pc_sctd
```

## Result (SCTD held-out test, real boxes)
| threshold | recall | false pos/image |
|-----------|--------|-----------------|
| p95  | 100%  | 7.8 |
| p99  | 96.4% | 4.5 |
| p999 | 78.6% | 3.1 |

High-recall candidate generator; false positives are filtered by the downstream
shadow / physics / fusion stages. `PatchCore.detect()` emits candidate dicts in the
pipeline's shape (bbox + `p_cae`).
