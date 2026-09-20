# Component Guide: 12-Stage Master Pipeline

The **Master Pipeline** ([`master_pipeline_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/master_pipeline_service.py)) orchestrates the full analytical workflow from raw sonar image file upload to a comprehensive maritime intelligence report.

```
                 ┌──────────────────────────────────────┐
                 │ Raw Sonar (.xtf / .jsf) or Image File │
                 └──────────────────┬───────────────────┘
                                    ↓
                 1. Input Validation & Sonar Ingestion
                    (XTF/JSF -> Waterfall Raster -> BGR)
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

### Stage 1: Input Validation & Sonar Ingestion
- **Engines**: [`input_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/input_service.py) & [`sonar_ingestion_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/sonar_ingestion_service.py)
- **Dual-Path Handling**:
  - **Standard Image Path**: Verifies file size ($\le 100\text{MB}$), MIME magic bytes (JPEG, PNG, WEBP, BMP, TIFF), dimensions ($32\text{px}$ to $12,000\text{px}$), and decodes into a clean OpenCV BGR array.
  - **Raw Sonar Path (`.xtf`, `.jsf`)**: Detects file signature, executes format parser ([`XtfSonarParser`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/xtf_reader.py) or [`JsfSonarParser`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/jsf_reader.py)), synthesizes a normalized 2D acoustic waterfall raster via [`SonarRasterBuilder`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/raster_reader.py), converts the `uint8` grayscale matrix to 3-channel BGR image format, and extracts [`SonarMetadataContext`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) (channels, nadir column, slant range, GSD, valid navigation fixes).


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
  - Raw sonar provenance context ([`SonarMetadataContext`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py)) when ingesting `.xtf` or `.jsf` files.

---

## Dual Input Path Convergence & Unified Sonar Analysis Contract (Phase 6A)

MarineScan supports two distinct ingestion workflows that seamlessly converge before the core analytical stages:

```
XTF / JSF Raw Sonar                     Standard Marine Imagery (PNG / JPG / TIFF)
         │                                                  │
         ▼                                                  ▼
1. Format Parser (Xtf / Jsf)                     1. Input Service (MIME & Decode)
         │                                                  │
         ▼                                                  │
2. Waterfall Raster Builder                                 │
         │                                                  │
         ▼                                                  │
3. Sonar Ingestion Service                                  │
         │                                                  │
         └────────────────────────┬─────────────────────────┘
                                  │
                                  ▼
                     12-Stage Master Pipeline
              (Quality → Preprocessing → YOLO11 →
               Shadows → Physics → Confidence →
               Geolocation → Dimensions → Risk)
                                  │
                                  ▼
                     SonarAnalysisResponse Contract
```

### `SonarAnalysisResponse` Schema Structure

The unified contract is exposed through [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py):

| Section | Model | Description |
|---|---|---|
| `source` | [`AnalysisSourceInfo`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) | Input provenance: `filename`, `format` (`XTF`, `JSF`, `PNG`, `JPEG`), `file_size` |
| `sonar` | [`SonarRasterMetadata`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) | Acoustic raster metadata: `total_pings`, `waterfall_width`, `waterfall_height`, `nadir_pixel`, `meters_per_pixel`, `raster_reference` (`/api/v1/sonar/raster`), `coordinate_convention`. (`None` for standard images) |
| `navigation` | [`SonarNavigation`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/sonar.py) | Normalized GPS & telemetry fix: `latitude`, `longitude`, `heading`, `depth`, `altitude`. Missing values strictly `null` (no `0.0, 0.0` fallbacks). (`None` for standard images) |
| `analysis` | [`MasterAnalysisResult`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) | Full 12-stage intelligence report: `targets`, `geojson`, `summary`, `timings`, `quality_assessment`. Lightweight: `annotated_image_base64` is omitted by default |
| `warnings` | `List[str]` | Non-fatal parser anomalies or pipeline warnings |

### Pixel Coordinate Convention

All pixel coordinates for detections, bounding boxes, and acoustic shadows align directly with the waterfall raster:
- **Origin `(0, 0)`**: Top-left corner of the waterfall image.
- **X Axis (Across-Track)**: Horizontal pixel column $x \in [0, \text{waterfall\_width} - 1]$. Center nadir ground-track is located at `nadir_pixel`.
- **Y Axis (Along-Track)**: Vertical pixel row / ping index $y \in [0, \text{waterfall\_height} - 1]$, progressing chronologically along the survey track.

---

## API Endpoints & Cross-Platform Invocations

- **`POST /api/v1/analyses/analyze`**: Run the complete 12-stage Master Pipeline on image or raw sonar files (returns [`MasterAnalysisResult`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py)).
- **`POST /api/v1/analyses/sonar`**: Unified raw `.xtf` / `.jsf` sonar pipeline execution (returns [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py)).
- **`POST /api/v1/analyses/visualize`**: Stream directly an annotated JPEG visual overlay.

### Full Pipeline Analysis Example (Standard Image)

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

### Raw Sonar Pipeline Execution (`.xtf` / `.jsf`)

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/sonar?max_pings=1500&channels=0,1" \
  -F "file=@survey_line_01.xtf" \
  -F "confidence_threshold=0.25"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "survey_line_01.xtf"
    confidence_threshold = "0.25"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analyses/sonar?max_pings=1500&channels=0,1" -Method Post -Form $form
```


