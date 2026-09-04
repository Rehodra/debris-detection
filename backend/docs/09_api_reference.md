# Complete API Reference: All 25 REST Endpoints

The MarineScan backend exposes **25 documented REST endpoints** under `/api/v1/` and root `/`. All endpoints are documented in the interactive Swagger UI at **`http://localhost:8000/docs`**.

---

## 1. Master Pipeline Endpoints (`/api/v1/analyses`)

### `POST /api/v1/analyses/analyze`
Executes the full 12-stage Master Pipeline.
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Raw sonar image file (binary)
  - `vessel_lat` (float, default $24.8607$): Survey vessel latitude
  - `vessel_lon` (float, default $67.0011$): Survey vessel longitude
  - `vessel_heading_deg` (float, default $0.0$): Vessel gyro heading ($0^\circ - 360^\circ$)
  - `water_depth_m` (float, default $30.0$): Water depth in meters
  - `meters_per_pixel` (float, default $0.05$): Ground Sampling Distance (GSD)
  - `nadir_x` (float, optional): Nadir ground-track pixel coordinate
  - `cable_payout_m` (float, optional): Towfish cable payout in meters
  - `fish_depth_m` (float, optional): Towfish operating depth in meters
  - `confidence_threshold` (float, default $0.25$): Detection threshold
  - `preprocessing_preset` (string, default `"sonar_acoustic"`): Acoustic preset
  - `use_tiling` (bool, default `false`): Enable sliding-window tiling
- **Response**: `200 OK` $\rightarrow$ [`MasterAnalysisResult`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py)

### `POST /api/v1/analyses/visualize`
Executes Master Pipeline and streams directly the rendered JPEG binary overlay.
- **Content-Type**: `multipart/form-data`
- **Response**: `200 OK` $\rightarrow$ `image/jpeg`

---

## 2. Detection Endpoints (`/api/v1/detections`)

### `POST /api/v1/detections/predict`
Single-image YOLOv8 inference with optional preprocessing and physical scaling.
- **Response**: `200 OK` $\rightarrow$ `DetectionResponse`

### `POST /api/v1/detections/predict-batch`
Parallel batched inference across multiple uploaded images.
- **Response**: `200 OK` $\rightarrow$ `BatchDetectionResponse`

### `POST /api/v1/detections/visualize`
Returns binary JPEG render with color-coded bounding boxes and confidence badges.
- **Response**: `200 OK` $\rightarrow$ `image/jpeg`

---

## 3. Acoustic Preprocessing Endpoints (`/api/v1/preprocessing`)

### `GET /api/v1/preprocessing/presets`
Lists all 6 enhancement presets (`sonar_acoustic`, `turbid_water`, `balanced`, `edge_enhance`, `raw_normalize`, `fast`).
- **Response**: `200 OK` $\rightarrow$ `PresetsListResponse`

### `POST /api/v1/preprocessing/process`
Applies custom denoising, CLAHE, gamma, and colormapping; returns quality telemetry.
- **Response**: `200 OK` $\rightarrow$ `PreprocessingResponse`

### `POST /api/v1/preprocessing/preview`
Applies preprocessing and directly streams the enhanced JPEG binary.
- **Response**: `200 OK` $\rightarrow$ `image/jpeg`

---

## 4. Acoustic Shadow Endpoints (`/api/v1/shadows`)

### `POST /api/v1/shadows/analyze`
Extracts acoustic shadow candidates, evaluates nadir ray alignment, and computes 3D height off seabed.
- **Response**: `200 OK` $\rightarrow$ `BatchShadowResponse`

### `POST /api/v1/shadows/visualize`
Renders cyan shadow polygons and yellow projection rays on the image.
- **Response**: `200 OK` $\rightarrow$ `image/jpeg`

---

## 5. Ocean Physics Endpoints (`/api/v1/physics`)

### `GET /api/v1/physics/environment`
Computes Mackenzie speed of sound in seawater, acoustic absorption ($\alpha$), and wavelength ($\lambda$).
- **Parameters**: `temperature_c` (float), `salinity_psu` (float), `depth_m` (float), `frequency_khz` (float).
- **Response**: `200 OK` $\rightarrow$ `OceanAcousticEnvironment`

### `POST /api/v1/physics/analyze-target`
Computes 3D volume, mass, crane hoist rating, and seabed stability for a single target.
- **Response**: `200 OK` $\rightarrow$ `TargetPhysicsAnalysis`

### `POST /api/v1/physics/analyze-image`
End-to-end detection + shadow + physics synthesis from uploaded sonar image.
- **Response**: `200 OK` $\rightarrow$ `BatchPhysicsResponse`

---

## 6. Confidence Calibration Endpoints (`/api/v1/confidence`)

### `POST /api/v1/confidence/evaluate-target`
Computes multi-pillar confidence fusion (AI + Physics + Quality) and trust tier for a specific target.
- **Response**: `200 OK` $\rightarrow$ `TargetConfidenceProfile`

### `POST /api/v1/confidence/analyze-image`
End-to-end detection + shadow + physics + confidence calibration from uploaded sonar image.
- **Response**: `200 OK` $\rightarrow$ `BatchConfidenceResponse`

---

## 7. Geolocation Endpoints (`/api/v1/geolocation`)

### `POST /api/v1/geolocation/layback`
Computes true towfish position astern of surface vessel from cable payout and depth.
- **Response**: `200 OK` $\rightarrow$ `GeoCoordinates`

### `POST /api/v1/geolocation/target`
Geolocates a single pixel target into WGS84, DMS, and UTM coordinates.
- **Response**: `200 OK` $\rightarrow$ `GeolocatedTarget`

### `POST /api/v1/geolocation/analyze-image`
End-to-end detection + geolocation + RFC 7946 GeoJSON FeatureCollection export.
- **Response**: `200 OK` $\rightarrow$ `BatchGeolocationResponse`

---

## 8. Maritime Risk Endpoints (`/api/v1/risk`)

### `POST /api/v1/risk/evaluate-target`
Computes under-keel draft clearance, trawl snag risk, and action recommendations.
- **Response**: `200 OK` $\rightarrow$ `TargetRiskAssessment`

### `POST /api/v1/risk/analyze-image`
End-to-end detection + clearance + risk scoring + NOTMAR directives.
- **Response**: `200 OK` $\rightarrow$ `BatchRiskResponse`

---

## 9. Model Management & Health Endpoints

### `GET /api/v1/models/current`
Returns active model architecture, compute device (`mps`, `cuda`, `cpu`), and class list.

### `GET /api/v1/models/classes`
Returns metadata, display names, hazard levels, and color tokens for all classes.

### `POST /api/v1/models/reload`
Hot-reloads neural model weights from disk.

### `GET /api/v1/health`
System health check and model loading status.

### `GET /`
Root service information and documentation links.
