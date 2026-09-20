# Component Guide: Raw Sonar Ingestion Engine (.xtf & .jsf)

The **Raw Sonar Ingestion Engine** provides native, hardware-accurate binary parsing and acoustic waterfall raster synthesis for industry-standard hydrographic survey recordings:
- **Extended Triton Format (`.xtf`)**: The standard exchange format for multi-channel sidescan sonar, sub-bottom profilers, and bathymetry systems.
- **EdgeTech JSF (`.jsf`)**: EdgeTech's proprietary packet-based telemetry and acoustic acquisition protocol.

It functions as an **upstream adapter** into MarineScan's 12-stage Master Intelligence Pipeline, translating raw acoustic sample streams and navigation packets into normalized raster imagery without requiring external third-party conversion utilities.

---

## 1. Subsystem Architecture & Ingestion Flow

```
                      ┌─────────────────────────────────┐
                      │ Raw Survey File (.xtf / .jsf)   │
                      └────────────────┬────────────────┘
                                       │
                         [Format Signature Detection]
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
     ┌──────────────────────┐                      ┌──────────────────────┐
     │   XtfSonarParser     │                      │   JsfSonarParser     │
     │  - 1024-byte header  │                      │  - 16-byte protocol  │
     │  - ChanInfo structs  │                      │  - Message Type 80   │
     │  - Type 0 ping pkts  │                      │  - Navigation pings  │
     └──────────┬───────────┘                      └──────────┬───────────┘
                │                                             │
                └──────────────────────┬──────────────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │      SonarRasterBuilder       │
                       │ - 2nd-98th %ile normalization │
                       │ - NaN/Inf sanitization        │
                       │ - Slant-range zero padding    │
                       │ - Port (rev) + Starboard (un) │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │     SonarMetadataContext      │
                       │ - Nadir pixel column          │
                       │ - Calculated GSD (m/pixel)    │
                       │ - Validated WGS84 coordinates │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │ Master Intelligence Pipeline  │
                       │   (Stages 2 through 12)       │
                       └───────────────────────────────┘
```

---

## 2. Supported Survey Formats

### A. Extended Triton Format (`.xtf`)
- **Implementation**: [`app.sonar.xtf_reader.XtfSonarParser`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/xtf_reader.py)
- **File Header Structure**:
  - Magic byte signatures: `0xFACE` (File Header), `0x0123` (Alt Magic).
  - 1024-byte `XTFFileHeader` followed by up to 6 `XTFChanInfo` structs (128 bytes each).
  - Ping packets begin with `XTFPingHeader` (Packet Type `0` for sidescan data).
- **Acoustic Samples**:
  - Decodes 8-bit, 16-bit, and 32-bit unsigned/signed sample streams.
  - Interleaved Port (Channel 0) and Starboard (Channel 1) channels.
- **Sensor Telemetry**:
  - Towfish depth, towfish altitude, sensor slant range, and sound speed.
  - Vessel and towfish navigation coordinates (degrees or projected units).

### B. EdgeTech JSF (`.jsf`)
- **Implementation**: [`app.sonar.jsf_reader.JsfSonarParser`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/jsf_reader.py)
- **Packet Structure**:
  - 16-byte protocol message header starting with sync marker `0x1601`.
  - Parses **Message Type 80** (Sidescan Sonar Acoustic Trace Data).
  - Handles 16-bit integer acoustic sample streams and subsampled envelope traces.
- **Sensor Telemetry**:
  - Ping timestamps (year, day of year, millisecond of day).
  - Towfish altitude ($m$), towfish depth ($m$), vessel gyro heading ($0.01^\circ$ resolution).
  - Navigation fixes encoded as integer coordinates (minutes of arc or raw units).

---

## 3. Acoustic Waterfall Synthesis (`SonarRasterBuilder`)

Raw sidescan sonar pings consist of variable-length acoustic backscatter intensity arrays recorded across time. The [`SonarRasterBuilder`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/sonar/raster_reader.py) converts raw ping arrays into a uniform 2D along-track waterfall raster:

1. **Channel Orientation & Nadir Alignment**:
   - **Dual-Channel Mode**: Port channel is horizontally mirrored (reversed) on the left half; Starboard channel is placed unreversed on the right half. The center seam marks the exact nadir ground-track column.
   - **Single-Channel Mode**: Supports Port-only (nadir at right margin) and Starboard-only (nadir at left margin).
2. **Deterministic Percentile Normalization**:
   - Computes robust 2nd-percentile ($p_2$) and 98th-percentile ($p_{98}$) intensity thresholds to eliminate acoustic speckle spikes and transmission dropouts without human tuning.
   - Stretches intensity linearly into 8-bit dynamic range $[0, 255]$:
     $$I_{\text{norm}} = 255 \times \frac{\text{clamp}(I, p_2, p_{98}) - p_2}{p_{98} - p_2}$$
3. **Robust Sanitization**:
   - Sanitizes `NaN`, `+Inf`, `-Inf`, and negative values to $0$.
   - Pads differing scanline sample lengths with zero-intensity values so asymmetric pings align without distorting nadir geometry.
4. **Memory Bounding (`max_pings`)**:
   - Enforces an optional upper bound on ingested along-track pings to ensure bounded memory consumption on massive survey files.

---

## 4. Navigation & Geodetic Integrity Safeguards

MarineScan strictly enforces navigation data integrity to prevent erroneous coordinates in maritime intelligence reports:

| Condition | Behavior |
|---|---|
| **Missing Navigation** | Output fields strictly remain `None` (`latitude = None`, `longitude = None`). |
| **Null Island Sentinels** | Exact `(0.0, 0.0)` coordinates are rejected as unlogged sentinels and treated as `None`. |
| **Fabricated Fallbacks** | Default coordinates (e.g. project office, harbor centroids) are **never** substituted. |
| **Invalid Ranges** | Latitudes outside $[-90^\circ, 90^\circ]$ or longitudes outside $[-180^\circ, 180^\circ]$ are discarded with parser warnings. |

---

## 5. Pipeline Integration & Provenance Context

When a raw `.xtf` or `.jsf` survey file enters Stage 1 of the Master Intelligence Pipeline:
1. `SonarIngestionService` converts the 1-channel `uint8` waterfall raster into a 3-channel BGR image (`cv2.COLOR_GRAY2BGR`).
2. Minimum dimension guards ($\ge 32\text{px}$) edge-pad short along-track bursts to prevent downstream Laplacian and Gaussian filter crashes.
3. Injected resolution (`meters_per_pixel`), nadir column, and valid navigation fixes calibrate Stages 6–10 (Shadows, Physics, Geolocation, Dimensions).
4. The final [`MasterAnalysisResult`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) includes a structured [`SonarMetadataContext`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py#L32-L46):

```json
{
  "sonar_metadata": {
    "sonar_format": "XTF",
    "original_filename": "survey_line_01.xtf",
    "total_pings": 1250,
    "channel_count": 2,
    "selected_channels": [0, 1],
    "waterfall_width": 2048,
    "waterfall_height": 1250,
    "channel_layout": "port_starboard",
    "nadir_pixel": 1024.0,
    "meters_per_pixel": 0.0488,
    "slant_range_m": 50.0,
    "navigation": {
      "latitude": 24.860732,
      "longitude": 67.001145,
      "heading_deg": 45.2,
      "altitude_m": 8.5,
      "depth_m": 22.0
    },
    "parser_warnings": []
  }
}
```

---

## 6. API Endpoints

### 1. `POST /api/v1/sonar/inspect`
Fast diagnostic header and metadata inspection.
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/sonar/inspect" -F "file=@survey.xtf"
  ```

### 2. `POST /api/v1/sonar/raster`
Generate and stream normalized acoustic waterfall raster (PNG binary or base64 JSON).
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/sonar/raster?max_pings=1000&as_image=true" \
    -F "file=@survey.jsf" \
    --output waterfall.png
  ```

### 3. `POST /api/v1/analyses/sonar`
Execute full 12-stage Master Intelligence Pipeline on raw sonar recording and return the unified [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py).
- **Parameters**:
  - `file`: Raw sonar survey recording (`.xtf` or `.jsf`)
  - `max_pings` (int, optional): Cap along-track pings
  - `channels` (str, optional): Target channels (e.g. `"0,1"`)
  - `return_visualization` (bool, optional, default `false`): By default returns lightweight JSON (< 50 KB) without embedding large base64 rasters.
- **cURL**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/analyses/sonar?max_pings=1000&channels=0,1" \
    -F "file=@survey.xtf" \
    -F "confidence_threshold=0.25"
  ```

---

## 7. Unified Sonar Analysis Response Contract (Phase 6A)

The unified response model [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py) standardizes how frontend applications consume acoustic survey intelligence:

```json
{
  "status": "success",
  "source": {
    "filename": "survey.xtf",
    "format": "XTF",
    "file_size": 1048576,
    "file_size_bytes": 1048576
  },
  "sonar": {
    "artifact_id": "art_msn_4a1b2c3d4e",
    "total_pings": 1500,
    "channel_count": 2,
    "selected_channels": [0, 1],
    "channel_layout": "port_starboard",
    "waterfall_width": 2048,
    "waterfall_height": 1500,
    "nadir_pixel": 1024.0,
    "meters_per_pixel": 0.05,
    "slant_range_m": 50.0,
    "raster_reference": "/api/v1/analyses/msn_4a1b2c3d4e/sonar/raster",
    "coordinate_convention": "top_left_origin_x_across_y_along"
  },
  "navigation": {
    "latitude": 24.8607,
    "longitude": 67.0011,
    "heading": 180.0,
    "altitude": 15.0,
    "depth": 5.0
  },
  "analysis": {
    "mission_id": "msn_4a1b2c3d4e",
    "summary": { ... },
    "timings": { ... },
    "targets": [ ... ],
    "geojson": { ... },
    "quality_assessment": { ... }
  },
  "warnings": []
}
```

### Pixel Coordinate Convention
- **Origin `(0, 0)`**: Top-left pixel of the waterfall raster.
- **Across-Track Coordinate ($X$)**: Horizontal pixel column $x \in [0, \text{waterfall\_width} - 1]$. Center nadir ground-track is located at `nadir_pixel`.
- **Along-Track Coordinate ($Y$)**: Vertical pixel row / ping index $y \in [0, \text{waterfall\_height} - 1]$.

---

## 8. Stable Analysis Artifact & Raster Retrieval (Phase 6B)

Completed raw sonar analyses establish a deterministic, 1:1 relationship between the analysis identity (`mission_id`), the original acoustic recording, and the resulting waterfall raster:

```
                XTF / JSF
                    │
                    ▼
          SonarIngestionService
                    │
                    ▼
            Waterfall Raster
                    │
                    ▼
          SonarArtifactService  (saves lossless PNG + sidecar JSON)
                    │
                    ▼
               Analysis ID
                    │
      ┌─────────────┴─────────────┐
      ▼                           ▼
Analysis JSON (lightweight)   Waterfall Raster Artifact (PNG)
- raster_reference             - exact original dimensions
- artifact_id                  - preserved channels & max_pings
- acquisition telemetry        - HTTP streaming at:
                                 GET /api/v1/analyses/{analysis_id}/sonar/raster
```

### Key Retrieval Endpoint Features:
- **Zero Base64 Overhead**: The waterfall image is never embedded as base64 in the analysis JSON.
- **Deterministic Reproducibility**: The raster returned is the exact artifact generated during analysis with the exact `max_pings` and `channels` selected—never dynamically regenerated from defaults.
- **Acquisition Telemetry Headers**: Responses include `X-Analysis-ID`, `X-Artifact-ID`, `X-Raster-Width`, `X-Raster-Height`, `X-Channel-Layout`, `X-Total-Pings`, `X-Sonar-Format`, `X-Nadir-Pixel-X`, `X-Meters-Per-Pixel`, `X-Slant-Range-M`, and `X-Sonar-Metadata`.
- **Strict Isolation & Error Handling**: Invalid IDs or non-sonar analyses return clean 404 responses. Missing storage files return 404 with descriptive diagnostics without silent fallback.

---

## 9. Command Line Diagnostic Utilities

Two standalone command-line scripts are available for direct terminal inspection:

```bash
cd backend

# Inspect XTF survey files:
python -m app.sonar.inspect_xtf path/to/survey.xtf

# Inspect EdgeTech JSF survey files:
python -m app.sonar.inspect_jsf path/to/survey.jsf
```

---

## 10. Verification & Test Suite

The raw sonar subsystem is validated across **100 dedicated tests** spanning 8 automated test modules:

| Test Module | Test Focus | Tests Passed | Skips |
|---|---|:---:|:---:|
| `test_sonar_base.py` | Schema validation, navigation boundary rules, exception hierarchy | 17 | 0 |
| `test_xtf_parser.py` | XTF header decoding, ping packets, error handling | 10 | 1* |
| `test_jsf_parser.py` | JSF message parsing, type 80 packets, error handling | 10 | 1* |
| `test_sonar_raster.py` | Waterfall generation, normalization, channel layouts, nadir alignment | 16 | 0 |
| `test_sonar_api.py` | REST endpoints (`/sonar/inspect` and `/sonar/raster`) | 11 | 0 |
| `test_sonar_pipeline_integration.py` | End-to-end pipeline execution with raw sonar, metadata propagation | 14 | 0 |
| `test_sonar_analysis_contract.py` | Unified SonarAnalysisResponse contract, XTF/JSF/PNG, navigation, coordinates | 9 | 0 |
| `test_sonar_artifact_retrieval.py` | Phase 6B: Stable artifact creation, retrieval, metadata consistency, cleanup | 12 | 0 |

*\*Expected skips: Physical real-world `.xtf` and `.jsf` survey recordings are not yet present in the repository.*

