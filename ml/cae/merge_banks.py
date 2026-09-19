"""Merge marine seabed patch banks (SCTD + KLSG) into one combined training set.

Keeps SCTD's val split for calibration so detection thresholds stay matched to the
marine test domain. Patch size must match across sources (both 64px).
"""

import sys
from pathlib import Path

import numpy as np

sctd = np.load(sys.argv[1])   # ml/cae/runs/pc_sctd/patches.npz  (train, val)
klsg = np.load(sys.argv[2])   # ml/cae/runs/cae_klsg/patches.npz (train, val, test)
out = Path(sys.argv[3])

assert sctd["train"].shape[1:] == klsg["train"].shape[1:], "patch sizes differ"
train = np.concatenate([sctd["train"], klsg["train"]])
val = sctd["val"]             # calibrate on SCTD (the domain we test on)
out.mkdir(parents=True, exist_ok=True)
np.savez_compressed(out / "patches.npz", train=train, val=val,
                    test=np.zeros((0, train.shape[1], train.shape[2]), np.uint8))
print(f"combined train={len(train)} (SCTD {len(sctd['train'])} + KLSG {len(klsg['train'])}), "
      f"val={len(val)} (SCTD)")
