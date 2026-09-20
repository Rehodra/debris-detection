# MarineScan — Geolocation & Coordinate Integrity Report

**Date:** 2026-09-20 09:37:40 UTC  
**Standards:** WGS84 (EPSG:4326), RFC 7946 GeoJSON  

---

## 1. Coordinate Integrity Overview

This report documents the verification of geographic positioning across all validation runs, ensuring that:
1. Coordinates exist when sensor navigation packets or vessel fixes are provided.
2. Formats strictly comply with WGS84 standards (Latitude [-90, 90], Longitude [-180, 180]).
3. RFC 7946 GeoJSON exports strictly adhere to the `[longitude, latitude]` coordinate order standard.
4. **No fallback to (0,0) (Null Island):** Unnavigated or sentinel coordinates are strictly preserved as `null` and never fabricated.

---

## 2. Geolocation Verification Table

| Dataset | Mission ID | Target ID | Latitude (°N) | Longitude (°E) | Valid WGS84 | Layback Applied | Null Island Guard |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| Real XTF Small (15CCT03_SSS_153_150602154100) | `msn_4d3cdd8b98` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| Real XTF Medium (15CCT03_SSS_153_150602154200) | `msn_885849271d` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| Real XTF Large (15CCT03_SSS_153_150602144500) | `msn_9c312d395a` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| EdgeTech JSF Small (synthetic_small) | `msn_ba9848e2d4` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| EdgeTech JSF Medium (synthetic_medium) | `msn_c5fef1a317` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| EdgeTech JSF Null Island (null_island) | `msn_5d0d7c4285` | *(No targets)* | — | — | N/A | N/A | **PROTECTED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_cb6537dd` | 24.86048 | 67.00163 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_1eb5c144` | 24.86056 | 67.00142 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_6a93796a` | 24.86049 | 67.00141 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_61da625b` | 24.86077 | 67.00132 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_ba76774b` | 24.86060 | 67.00143 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_ec7cdad0` | 24.86108 | 67.00138 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Lucinda van Valkenburg) | `msn_0b56bc5215` | `det_fe906917` | 24.86058 | 67.00143 | YES | NO | **NEUTRALIZED** |
| Side-Scan Shipwreck (Viator) | `msn_ed6c4ac362` | `det_9a0077ce` | 24.86080 | 67.00160 | YES | NO | **NEUTRALIZED** |

---

## 3. RFC 7946 GeoJSON Export Conformance

All generated GeoJSON export packages were verified against the IETF RFC 7946 specification:
- Coordinate elements are ordered as `[longitude, latitude]`.
- Feature geometries are valid GeoJSON `Point` features for targets and `LineString` features for acquisition tracks.
- Property payloads carry target classifications, confidence ratings, physical dimensions, and risk tiers.
