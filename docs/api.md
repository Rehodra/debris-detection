# MarineScan REST API Specification & Developer Guide

The MarineScan API provides 28 production-ready REST endpoints for raw sidescan sonar ingestion (.xtf / .jsf), waterfall raster generation, YOLO11 neural detection, acoustic shadow corroboration, hydrographic physics modeling, WGS84 geodesy, and maritime risk assessment.

- **Base URL**: `http://localhost:8000`
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON Schema**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 1. Master Pipeline Endpoints (`/api/v1/analyses`)

### `POST /api/v1/analyses/analyze`
Executes the full 12-stage Master Pipeline on an uploaded sidescan sonar waterfall image or raw `.xtf` / `.jsf` survey file.

- **Content-Type**: `multipart/form-data`
- **Form Parameters**:
  | Parameter | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `file` | Binary File | Yes | — | Sonar image (`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`) or raw survey file (`.xtf`, `.jsf`) |
  | `vessel_lat` | Float | No | `24.8607` | Survey vessel GNSS latitude (degrees) |
  | `vessel_lon` | Float | No | `67.0011` | Survey vessel GNSS longitude (degrees) |
  | `vessel_heading_deg` | Float | No | `0.0` | Gyro heading ($0^\circ - 360^\circ$) |
  | `water_depth_m` | Float | No | `30.0` | Seafloor bathymetric depth (meters) |
  | `meters_per_pixel` | Float | No | `0.05` | Sensor Ground Sampling Distance (GSD) |
  | `nadir_x` | Float | No | Auto | Center nadir track pixel coordinate |
  | `cable_payout_m` | Float | No | `0.0` | Towfish cable payout length (meters) |
  | `fish_depth_m` | Float | No | `0.0` | Towfish sensor operating depth (meters) |
  | `confidence_threshold` | Float | No | `0.25` | Neural detection probability cutoff |
  | `preprocessing_preset` | String | No | `"sonar_acoustic"` | Denoising and contrast preset |
  | `use_tiling` | Boolean | No | `false` | Sliding-window tiling for high-res waterfalls |

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/analyze" \
  -F "file=@backend/sample_sidescan.png" \
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
    file = Get-Item "backend\sample_sidescan.png"
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

---

### `POST /api/v1/analyses/sonar`
Executes the full 12-stage Master Pipeline on an uploaded raw `.xtf` or `.jsf` survey recording and returns the unified `SonarAnalysisResponse`.

- **Content-Type**: `multipart/form-data`
- **Response**: `200 OK` $\rightarrow$ `SonarAnalysisResponse` (`source`, `sonar`, `navigation`, `analysis`, `warnings`)
- **Query / Form Parameters**:
  | Parameter | Type | Required | Default | Description |
  |---|---|---|---|---|
  | `file` | Binary File | Yes | — | Raw sonar survey file (`.xtf` or `.jsf`) |
  | `max_pings` | Integer | No | `None` | Optional limit on along-track pings ingested |
  | `channels` | String | No | `None` | Comma-separated channel indices to assemble (e.g. `"0,1"`) |
  | `return_visualization` | Boolean | No | `false` | When `false`, returns lightweight JSON without embedded base64 image |
  | `vessel_lat` | Float | No | Auto | Fallback latitude if unlogged in survey packets |
  | `vessel_lon` | Float | No | Auto | Fallback longitude if unlogged in survey packets |
  | `confidence_threshold` | Float | No | `0.25` | Neural detection probability cutoff |

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/sonar?max_pings=1000&channels=0,1" \
  -F "file=@survey_line_01.xtf" \
  -F "confidence_threshold=0.30"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "survey_line_01.xtf"
    confidence_threshold = "0.30"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analyses/sonar?max_pings=1000&channels=0,1" -Method Post -Form $form
```

---

### `POST /api/v1/analyses/visualize`
Executes the master pipeline and streams directly the rendered JPEG binary overlay with detection bounding boxes, cyan shadow contours, and yellow acoustic projection vectors.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/visualize" \
  -F "file=@backend/sample_sidescan.png" \
  -F "water_depth_m=35.0" \
  --output pipeline_annotated.jpg
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    water_depth_m = "35.0"
}
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/analyses/visualize" -Method Post -Form $form -OutFile "pipeline_annotated.jpg"
```

---

## 2. Neural Detection Endpoints (`/api/v1/detections`)

- **`POST /api/v1/detections/predict`**: Single image inference using YOLO11 across the 7 subsea classes.
- **`POST /api/v1/detections/predict-batch`**: Multi-file batch inference.
- **`POST /api/v1/detections/visualize`**: Return binary JPEG with color-coded boxes and badges.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/detections/predict" \
  -F "file=@backend/sample_sidescan.png" \
  -F "confidence_threshold=0.25" \
  -F "meters_per_pixel=0.05"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    confidence_threshold = "0.25"
    meters_per_pixel = "0.05"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/detections/predict" -Method Post -Form $form
```

---

## 3. Acoustic Preprocessing Endpoints (`/api/v1/preprocessing`)

- **`GET /api/v1/preprocessing/presets`**: List all 6 enhancement presets.
- **`POST /api/v1/preprocessing/process`**: Apply custom filtering, CLAHE, gamma LUT, and colormaps; returns image telemetry (SNR, contrast, dynamic range).
- **`POST /api/v1/preprocessing/preview`**: Stream directly the enhanced JPEG image.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/preprocessing/preview" \
  -F "file=@backend/sample_sidescan.png" \
  -F "preset=sonar_acoustic" \
  --output enhanced_sample.jpg
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    preset = "sonar_acoustic"
}
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/preprocessing/preview" -Method Post -Form $form -OutFile "enhanced_sample.jpg"
```

---

## 4. Acoustic Shadow Endpoints (`/api/v1/shadows`)

- **`POST /api/v1/shadows/analyze`**: Extract acoustic shadows, evaluate nadir ray alignment, and calculate 3D height off seabed.
- **`POST /api/v1/shadows/visualize`**: Stream annotated JPEG with cyan shadow polygons and yellow projection rays.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/shadows/analyze" \
  -F "file=@backend/sample_sidescan.png" \
  -F "altitude_m=12.0" \
  -F "meters_per_pixel=0.05"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    altitude_m = "12.0"
    meters_per_pixel = "0.05"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/shadows/analyze" -Method Post -Form $form
```

---

## 5. Ocean Physics Endpoints (`/api/v1/physics`)

- **`GET /api/v1/physics/environment`**: Mackenzie speed of sound, acoustic absorption, and acoustic wavelength.
- **`POST /api/v1/physics/analyze-target`**: 3D volume, mass, crane hoist rating, and seabed stability for a single target.
- **`POST /api/v1/physics/analyze-image`**: Full detection + shadow + physics pipeline.

#### macOS / Linux (cURL)
```bash
curl -s "http://localhost:8000/api/v1/physics/environment?temperature_c=18.5&salinity_psu=35.0&depth_m=45.0&frequency_khz=455.0"
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/physics/environment?temperature_c=18.5&salinity_psu=35.0&depth_m=45.0&frequency_khz=455.0" -Method Get
```

---

## 6. Confidence Calibration Endpoints (`/api/v1/confidence`)

- **`POST /api/v1/confidence/evaluate-target`**: Multi-pillar confidence fusion (AI + Physics + Quality) and trust tier for a single target.
- **`POST /api/v1/confidence/analyze-image`**: End-to-end detection + confidence calibration.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/confidence/analyze-image" \
  -F "file=@backend/sample_sidescan.png" \
  -F "water_depth_m=30.0"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    water_depth_m = "30.0"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/confidence/analyze-image" -Method Post -Form $form
```

---

## 7. Geolocation Endpoints (`/api/v1/geolocation`)

- **`POST /api/v1/geolocation/layback`**: Calculate towfish geographic coordinate astern of surface ship.
- **`POST /api/v1/geolocation/target`**: Geolocate single pixel target to WGS84, Nautical DMS, and UTM.
- **`POST /api/v1/geolocation/analyze-image`**: End-to-end detection + geolocation + RFC 7946 GeoJSON export.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/geolocation/analyze-image" \
  -F "file=@backend/sample_sidescan.png" \
  -F "vessel_lat=24.8607" \
  -F "vessel_lon=67.0011" \
  -F "vessel_heading_deg=45.0"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    vessel_lat = "24.8607"
    vessel_lon = "67.0011"
    vessel_heading_deg = "45.0"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/geolocation/analyze-image" -Method Post -Form $form
```

---

## 8. Maritime Risk Endpoints (`/api/v1/risk`)

- **`POST /api/v1/risk/evaluate-target`**: Evaluate under-keel clearance, trawl snag risk, and action recommendations.
- **`POST /api/v1/risk/analyze-image`**: End-to-end detection + clearance + risk scoring + NOTMAR directives.

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/risk/analyze-image" \
  -F "file=@backend/sample_sidescan.png" \
  -F "water_depth_m=35.0"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "backend\sample_sidescan.png"
    water_depth_m = "35.0"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/risk/analyze-image" -Method Post -Form $form
```

---

## 9. Model Management & System Health

### `GET /api/v1/models/current`
Returns active model architecture, compute device (`mps`, `cuda`, `cpu`), and class list.

#### macOS / Linux
```bash
curl -s http://localhost:8000/api/v1/models/current
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/models/current" -Method Get
```

### `GET /api/v1/models/classes`
Returns metadata, display names, hazard tiers, and color tokens for all 7 classes.

### `POST /api/v1/models/reload`
Hot-reloads neural model weights from disk.

### `GET /api/v1/health`
System health check and model loading status.

---

## 10. Raw Sonar Endpoints (`/api/v1/sonar`)

### `POST /api/v1/sonar/inspect`
Fast diagnostic inspection of raw `.xtf` and `.jsf` survey files. Extracts file format, total pings, channel metadata, frequencies, sample rates, and representative navigation fix without the memory overhead of rendering full waterfalls.

- **Content-Type**: `multipart/form-data`
- **Form Parameters**:
  - `file`: Raw sonar survey file (`.xtf` or `.jsf`)
  - `max_pings` (integer, optional): Maximum pings to inspect
- **Response**: `200 OK` $\rightarrow$ `SonarInspectResponse`

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/sonar/inspect" \
  -F "file=@survey_line_01.xtf"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "survey_line_01.xtf"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sonar/inspect" -Method Post -Form $form
```

---

### `POST /api/v1/sonar/raster`
Generates a normalized 2D acoustic waterfall raster from an uploaded `.xtf` or `.jsf` survey recording. Supports direct PNG binary image streaming or structured base64 JSON output.

- **Content-Type**: `multipart/form-data`
- **Form Parameters**:
  - `file`: Raw sonar survey file (`.xtf` or `.jsf`)
  - `max_pings` (integer, optional): Bounded ping limit for memory management
  - `channels` (string, optional): Comma-separated channel indices (default `0,1`)
  - `as_image` (boolean, default `true`): If `true`, returns `image/png` binary stream; if `false`, returns `SonarRasterResponse` JSON with base64 raster.
- **Response**: `200 OK` $\rightarrow$ `image/png` or `SonarRasterResponse`

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/sonar/raster?max_pings=1000&as_image=true" \
  -F "file=@survey_line_01.jsf" \
  --output waterfall_raster.png
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "survey_line_01.jsf"
}
Invoke-WebRequest -Uri "http://localhost:8000/api/v1/sonar/raster?max_pings=1000&as_image=true" -Method Post -Form $form -OutFile "waterfall_raster.png"
```

---

## Error Handling & HTTP Status Codes

| Status Code | Description | Typical Cause |
|---|---|---|
| `200 OK` | Request succeeded | Valid file and parameters |
| `400 Bad Request` | Invalid image file or corrupt bytes | Unsupported format or corrupt raw sonar recording |
| `422 Unprocessable Entity` | Validation error | Missing required parameter or invalid type |
| `500 Internal Server Error` | Unexpected processing failure | Unhandled exception in pipeline service |
| `503 Service Unavailable` | Model failed to load | Weights file missing or corrupted |
