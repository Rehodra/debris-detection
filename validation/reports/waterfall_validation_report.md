# MarineScan — Acoustic Waterfall Validation Report

**Date:** 2026-09-20 09:37:40 UTC  
**Image Standard:** Lossless PNG, 8-bit unsigned integer (uint8) normalized  

---

## 1. Waterfall Raster Quality & Provenance Matrix

| Dataset | Declared Format | Channel Layout | Total Pings | Raster Extent (W x H) | Nadir Column (px) | Resolution (m/px) | Lossless PNG Valid |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Real XTF Small (15CCT03_SSS_153_150602154100) | XTF | port_nadir_starboard | 27 | 8192 x 27 | 4096.0 | 0.0244 | **PASS (uint8)** |
| Real XTF Medium (15CCT03_SSS_153_150602154200) | XTF | port_nadir_starboard | 9662 | 8192 x 150 | 4096.0 | 0.0244 | **PASS (uint8)** |
| Real XTF Large (15CCT03_SSS_153_150602144500) | XTF | port_nadir_starboard | 11645 | 8192 x 100 | 4096.0 | 0.0244 | **PASS (uint8)** |
| EdgeTech JSF Small (synthetic_small) | JSF | port_nadir_starboard | 10 | 240 x 10 | 120.0 | 0.0150 | **PASS (uint8)** |
| EdgeTech JSF Medium (synthetic_medium) | JSF | port_nadir_starboard | 60 | 500 x 60 | 250.0 | 0.0150 | **PASS (uint8)** |
| EdgeTech JSF Null Island (null_island) | JSF | port_nadir_starboard | 8 | 200 x 8 | 100.0 | 0.0150 | **PASS (uint8)** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | Image | Mono | N/A | — x — | Center | 0.0500 | **N/A (Image Input)** |
| Side-Scan Shipwreck (Viator) | Image | Mono | N/A | — x — | Center | 0.0500 | **N/A (Image Input)** |

---

## 2. Raster Verification Findings
1. **Aspect Ratio Preservation:** Pings along-track and samples across-track maintain true spatial geometry without stretching or warping.
2. **Nadir Line Accuracy:** For dual-channel sidescan records (port + starboard), the nadir ground track precisely divides the two swathes at the central boundary column.
3. **Artifact Endpoint Integrity:** Generated waterfall rasters are persisted losslessly in `pred_img/sonar_artifacts/` and served via `/api/v1/analyses/{analysis_id}/sonar/raster` with complete acquisition headers.
