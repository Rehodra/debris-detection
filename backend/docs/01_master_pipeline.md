# Component Guide: 12-Stage Master Pipeline

The **Master Pipeline** ([`master_pipeline_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/master_pipeline_service.py)) orchestrates the full analytical workflow from raw sonar image file upload to a comprehensive maritime intelligence report.

```
                 ┌───────────────┐
                 │ Uploaded File │
                 └───────┬───────┘
                         ↓
                 1. Input validation
                         ↓
                   2. Quality check
                         ↓
                   3. Preprocessing
                         ↓
                    4. YOLO11 Inference
                         ↓
                  5. Candidate list
                         ↓
                 6. Shadow evidence
                         ↓
                7. Physics validation
                         ↓
                8. Confidence fusion
                         ↓
                   9. Geolocation
                         ↓
                 10. Dimension estimate
                         ↓
                 11. Risk classification
                         ↓
                    12. Final result
```

---

## The 12 Stages in Detail

### Stage 1: Input Validation
- **Engine**: [`input_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/input_service.py)
- **Checks**:
  - File size: enforces $\le 100\text{MB}$ limit, rejects 0-byte uploads.
  - MIME magic byte signatures: verifies JPEG (`\xFF\xD8\xFF`), PNG (`\x89PNG`), WEBP (`RIFF....WEBP`), BMP (`BM`), or TIFF (`II*\x00` / `MM\x00*`).
  - Dimensions: confirms width and height are between $32\text{px}$ and $12,000\text{px}$.
  - Decoding: converts raw bytes to clean OpenCV BGR image array.

### Stage 2: Quality Check
- **Engine**: [`quality_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/quality_service.py)
- **Metrics**:
  - Laplacian focus variance ($\sigma^2$): flags acoustic defocus or vehicle motion smearing.
  - RMS contrast ($\sigma_I / \mu_I$): assesses dynamic visibility between targets and seabed.
  - Estimated Signal-to-Noise Ratio (SNR in dB).
  - Exposure clipping: detects acoustic blackout ($I \le 4$) and saturation ($I \ge 252$).
- **Output**: Overall quality score $\in [0, 1]$, quality tier (`PRISTINE`, `GOOD`, `ACCEPTABLE`, `DEGRADED`, `UNUSABLE`), and human-readable observations.

### Stage 3: Preprocessing
- **Engine**: [`preprocessing_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/preprocessing_service.py)
- **Operations**:
  - Acoustic speckle suppression (Bilateral or Median spatial filtering).
  - Contrast-Limited Adaptive Histogram Equalization (CLAHE in LAB color space).
  - Gamma lookup-table adjustment ($I' = 255 \cdot (I / 255)^\gamma$).
  - Curated enhancement presets (`sonar_acoustic`, `turbid_water`, `edge_enhance`, etc.).

### Stage 4: Neural Detection
- **Engine**: [`inference_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/inference_service.py)
- **Inference**:
  - Executes active Ultralytics YOLO11 model (`weights/yolo11_sonar_best.pt`, 5.20 MB).
  - 7-class subsea taxonomy: `shipwreck`, `pipe`, `ghost_net`, `marine_debris`, `aircraft`, `other`, `fish`.
  - Hardware acceleration: automatically binds to Apple Silicon `mps` on macOS, NVIDIA `cuda` on Windows/Linux, or `cpu`.
  - Supports high-resolution sliding-window tiling (`predict_tiled`) with **Global NMS** to prevent target truncation on large waterfall strips.

### Stage 5: Candidate List Extraction
- Formats raw neural detections into candidate records.
- Assigns unique identifiers (`det_xxxxxxxx`), normalized coordinates, and class metadata.
- Filters candidates based on operational confidence threshold.

### Stage 6: Acoustic Shadow Evidence
- **Engine**: [`shadow_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/shadow_service.py)
- **Acoustic Corroboration**:
  - Validates physical 3D seabed relief by detecting acoustic shadows directly behind high-reflectivity highlights.
  - Directional alignment: verifies shadow points radially away from the sonar nadir track.
  - Hydrographic elevation: computes true target height off seabed:
    $$h = \frac{L_{\text{shadow}} \cdot H_{\text{altitude}}}{R_{\text{slant}} + L_{\text{shadow}}}$$

### Stage 7: Physics Validation
- **Engine**: [`physics_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/physics_service.py)
- **Calculations**:
  - Mackenzie (1981) speed of sound in seawater, acoustic absorption ($\alpha$), wavelength ($\lambda$).
  - Slant-to-ground range Pythagorean conversion ($R_g = \sqrt{R_s^2 - H_{\text{alt}}^2}$) and grazing angles.
  - 3D volume, dry structural mass, Archimedes buoyant force ($F_B$), net submerged underwater weight ($W_{\text{submerged}}$), and **1.5× dynamic salvage crane lift ratings**.
  - Seabed current drag ($F_D$) vs. sediment holding friction ($F_f$) to compute Stability Index ($S_{\text{stability}}$) across 5 sediment types.

### Stage 8: Multi-Source Confidence Calibration
- **Engine**: [`confidence_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/confidence_service.py)
- **Fusion Model**:
  - $45\%$ AI model probability + $35\%$ Physics & shadow evidence + $20\%$ Acoustic image quality.
  - Applies dynamic noise gating and a $0.55\times$ penalty on physically implausible targets.
  - Outputs 4 operational trust tiers (`VERIFIED_TARGET`, `PROBABLE_DEBRIS`, `AMBIGUOUS_ANOMALY`, `SUSPECTED_FALSE_ALARM`).

### Stage 9: Geolocation & Navigation
- **Engine**: [`geolocation_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/geolocation_service.py)
- **Geodetic Operations**:
  - Calculates towfish catenary layback astern of surface vessel: $\text{Layback} = \sqrt{L_{\text{cable}}^2 - D_{\text{depth}}^2} \times k_{\text{catenary}}$.
  - Converts pixel centroid to across-track starboard/port and along-track offsets.
  - Rotates offsets by vessel gyro heading ($\theta \in [0^\circ, 360^\circ)$).
  - Outputs Decimal Degrees, Nautical DMS (`24° 51' 38.5" N`), UTM zones/easting/northing, and **RFC 7946 GeoJSON FeatureCollections**.

### Stage 10: Precision Dimension Scaling
- Derives physical metric length ($m$), width ($m$), shadow-derived height ($m$), seabed contact area ($m^2$), and 3D volumetric displacement ($m^3$).

### Stage 11: Maritime Risk Classification
- **Engine**: [`risk_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/risk_service.py)
- **Hazard Scoring**:
  - Evaluates under-keel water clearance ($\text{Clearance} = \text{Depth} - H_{\text{object}}$) against vessel drafts: shallow ($\le 3.5\text{m}$), medium ($\le 7.5\text{m}$), deep ($\le 15.0\text{m}$).
  - Evaluates commercial bottom trawl snag hazards (especially for `ghost_net` and `pipe`) and subsea pipeline collision risks.
  - Generates standardized directives: USCG/IMO NOTMAR alerts, IHO S-57 ENC chart obstruction updates, and ROV surveys.

### Stage 12: Final Result Synthesis
- Constructs [`MasterAnalysisResult`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py):
  - Per-target enriched intelligence records.
  - Sub-millisecond stage latency breakdown (`StageTimings`).
  - RFC 7946 `GeoJSONFeatureCollection` ready for web maps (`MissionMap.jsx`).
  - Executive summary with hazard tier counts and primary alert message.
  - Optional composite visual overlay (boxes + cyan shadow contours + yellow projection rays).

---

## API Endpoints & Cross-Platform Invocations

- **`POST /api/v1/analyses/analyze`**: Run the complete 12-stage Master Pipeline.
- **`POST /api/v1/analyses/visualize`**: Stream directly an annotated JPEG visual overlay.

### Full Pipeline Analysis Example

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/analyze" \
  -F "file=@sample_sidescan.png" \
  -F "vessel_lat=24.8607" \
  -F "vessel_lon=67.0011" \
  -F "vessel_heading_deg=45.0" \
  -F "water_depth_m=35.0" \
  -F "meters_per_pixel=0.05" \
  -F "confidence_threshold=0.25" \
  -F "preprocessing_preset=sonar_acoustic"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "sample_sidescan.png"
    vessel_lat = "24.8607"
    vessel_lon = "67.0011"
    vessel_heading_deg = "45.0"
    water_depth_m = "35.0"
    meters_per_pixel = "0.05"
    confidence_threshold = "0.25"
    preprocessing_preset = "sonar_acoustic"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analyses/analyze" -Method Post -Form $form
```
