# Complete API Reference: All 38 REST Endpoints

The MarineScan backend exposes **38 documented REST endpoints** under `/api/v1/` and root `/`. All endpoints are documented in the interactive Swagger UI at **`http://localhost:8000/docs`**.

---

## 1. Master Pipeline Endpoints (`/api/v1/analyses`)

### `POST /api/v1/analyses/analyze`
Executes the full 12-stage Master Pipeline on an uploaded sidescan sonar image (PNG, JPG, TIFF, BMP, WEBP) or raw survey recording (.xtf, .jsf).
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Raw sonar image or survey file (binary)
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

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/analyses/analyze" \
  -F "file=@sample_sidescan.png" \
  -F "vessel_lat=24.8607" \
  -F "vessel_lon=67.0011" \
  -F "confidence_threshold=0.25"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "sample_sidescan.png"
    vessel_lat = "24.8607"
    vessel_lon = "67.0011"
    confidence_threshold = "0.25"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/analyses/analyze" -Method Post -Form $form
```

### `POST /api/v1/analyses/sonar`
Executes the full 12-stage Master Pipeline on an uploaded raw `.xtf` or `.jsf` survey recording and returns the unified [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py).
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Raw sonar survey file (`.xtf` or `.jsf`)
  - `max_pings` (int, query parameter, optional): Maximum pings to ingest
  - `channels` (str, query parameter, optional): Comma-separated channel indices (`"0,1"`)
  - `return_visualization` (bool, query parameter, optional, default: `false`): When `false`, returns lightweight JSON without embedded base64 image; set to `true` to include base64 visual overlay.
  - `vessel_lat`, `vessel_lon`, `water_depth_m`, `confidence_threshold`: Form parameters
- **Response**: `200 OK` $\rightarrow$ [`SonarAnalysisResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/analysis.py)
  - `source`: `filename`, `format` (`XTF` / `JSF`), `file_size`
  - `sonar`: `total_pings`, `channel_count`, `waterfall_width`, `waterfall_height`, `nadir_pixel`, `meters_per_pixel`, `artifact_id`, `raster_reference` (`/api/v1/analyses/{analysis_id}/sonar/raster`), `coordinate_convention`
  - `navigation`: `latitude`, `longitude`, `heading`, `depth`, `altitude` (all optional, `null` when unavailable)
  - `analysis`: 12-stage intelligence result (`targets`, `geojson`, `summary`, `timings`, `quality_assessment`)
  - `warnings`: list of non-fatal anomalies or warnings
  - Top-level backward compatibility keys: `status`, `summary`, `timings`, `targets`, `sonar_metadata`

### `GET /api/v1/analyses/{analysis_id}/sonar/raster`
Retrieves the exact, immutable acoustic waterfall raster artifact generated during a completed raw sonar analysis (`.xtf` / `.jsf`) by its unique analysis ID (`mission_id`).
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `image/png`
- **Headers**:
  - `Content-Type`: `image/png`
  - `X-Analysis-ID`: Unique analysis identifier
  - `X-Artifact-ID`: Associated artifact identifier
  - `X-Raster-Width`: Across-track raster pixel width
  - `X-Raster-Height`: Along-track ping count / height
  - `X-Channel-Layout`: Acoustic channel arrangement (e.g. `port_nadir_starboard`)
  - `X-Total-Pings`: Total acoustic pings rendered
  - `X-Sonar-Format`: Raw recording format (`XTF` / `JSF`)
  - `X-Nadir-Pixel-X`: Ground-track nadir center column
  - `X-Meters-Per-Pixel`: Ground sampling distance in meters/pixel
  - `X-Slant-Range-M`: Recorded slant range extent
  - `X-Sonar-Metadata`: Full JSON string of acquisition and geometry telemetry
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found, analysis was not a raw sonar recording, or physical artifact file is missing from storage.

### `GET /api/v1/analyses/{analysis_id}/sonar/track`
Retrieves the ordered ping-by-ping navigation track and telemetry associated with a completed raw sonar analysis (.xtf / .jsf) by its unique analysis ID.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ [`SonarNavigationTrack`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/sonar.py) (`application/json`)
  - `analysis_id`: Unique analysis / mission identifier
  - `source_format`: Sonar format (`XTF` / `JSF`)
  - `total_pings`: Total ping records in the track
  - `available_navigation_pings`: Number of pings with valid WGS84 fixes
  - `points`: Ordered list of [`SonarPingTelemetry`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/sonar.py) objects in acquisition order (`ping_index`, `waterfall_row`, `timestamp`, `latitude`, `longitude`, `heading`, `altitude`, `depth`)
  - `warnings`: Ingestion/telemetry validation notices
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found, analysis was not a raw sonar recording, or physical track artifact is missing from storage.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/sonar/track" | jq .
```

---

### `POST /api/v1/analyses/visualize`
Executes Master Pipeline and streams directly the rendered JPEG binary overlay.
- **Content-Type**: `multipart/form-data`
- **Response**: `200 OK` $\rightarrow$ `image/jpeg`

---

## 2. Detection Endpoints (`/api/v1/detections`)

### `POST /api/v1/detections/predict`
Single-image YOLO11 inference (7 classes) with optional preprocessing and physical scaling.
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
Computes 3D volume, mass, crane hoist rating, and seabed stability for a single target across 7 subsea classes.
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

#### macOS / Linux
```bash
curl -s http://localhost:8000/api/v1/models/current
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/models/current" -Method Get
```

### `GET /api/v1/models/classes`
Returns metadata, display names, hazard levels, and color tokens for all 7 classes.

### `POST /api/v1/models/reload`
Hot-reloads neural model weights from disk.

### `GET /api/v1/health`
System health check and model loading status.

### `GET /`
Root service information and documentation links.

---

## 10. Raw Sonar Endpoints (`/api/v1/sonar`)

### `POST /api/v1/sonar/inspect`
Fast diagnostic inspection of raw `.xtf` and `.jsf` survey files. Extracts file format, total pings, channel metadata, frequencies, sample rates, and representative navigation fix without the memory overhead of rendering full waterfalls.
- **Content-Type**: `multipart/form-data`
- **Parameters**: `file` (binary), `max_pings` (int, query parameter, optional)
- **Response**: `200 OK` $\rightarrow$ [`SonarInspectResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/sonar.py)

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
Generates a normalized 2D acoustic waterfall raster from an uploaded `.xtf` or `.jsf` survey recording. Supports direct PNG binary streaming or structured base64 JSON output.
- **Content-Type**: `multipart/form-data`
- **Parameters**:
  - `file`: Raw sonar survey file (`.xtf` or `.jsf`)
  - `max_pings` (int, query parameter, optional): Bounded ping limit for memory management
  - `channels` (str, query parameter, optional): Comma-separated channel indices (default `0,1`)
  - `as_image` (bool, query parameter, default `true`): If `true`, returns `image/png` binary stream; if `false`, returns `SonarRasterResponse` JSON with base64 raster.
- **Response**: `200 OK` $\rightarrow$ `image/png` or [`SonarRasterResponse`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/schemas/sonar.py)

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

## 11. Hydrographic & Navigation Export Endpoints (`/api/v1/analyses/{analysis_id}/export`)

MarineScan Phase 7 introduces structured hydrographic dataset packaging for completed sonar and camera analyses. These endpoints operate strictly on stored analysis records, packaging intelligence without modifying upstream detection, physics, geolocation, or risk algorithms.

### `GET /api/v1/analyses/{analysis_id}/export/json`
Exports the complete structured hydrographic and navigation analysis package in JSON format.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `application/json`
- **Headers**:
  - `Content-Type`: `application/json`
  - `Content-Disposition`: `attachment; filename="marinescan_{analysis_id}.json"`
- **Schema Version**: `"1.0"`
- **Key Structure**:
  - `schema_version`: `"1.0"`
  - `analysis`: `analysis_id`, `original_filename`, `sonar_format`, `created_at`, `status`
  - `navigation`: `latitude`, `longitude`, `heading`, `depth`, `altitude`, `timestamp`, `source` (strictly `null` when unlogged; never fake coordinates or `0,0`)
  - `artifact`: `artifact_id`, `raster_reference`, `raster_width`, `raster_height`, `channel_layout`, `selected_channels`, `nadir_pixel_x`, `meters_per_pixel`, `slant_range_m` (`null` for camera analyses; strictly no base64 image data or internal server paths)
  - `summary`: full executive mission summary
  - `detections`: list of targets with `bbox` (pixel and normalized coordinates; origin top-left, X across-track, Y along-track), `geolocation` (WGS84, DMS, UTM), `dimensions`, `shadow`, and `risk`
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found or stored result unavailable.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/export/json" -O
```

---

### `GET /api/v1/analyses/{analysis_id}/export/csv`
Exports detection records from a completed survey analysis as a tabular CSV dataset.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `text/csv; charset=utf-8`
- **Headers**:
  - `Content-Type`: `text/csv; charset=utf-8`
  - `Content-Disposition`: `attachment; filename="marinescan_{analysis_id}.csv"`
- **Structure**: Single header row followed by one row per detection (or header only if 0 detections). Columns include `analysis_id`, `detection_id`, `class`, `confidence`, `x_min`, `y_min`, `x_max`, `y_max`, normalized coordinates, `latitude`, `longitude`, `dimensions`, `risk_score`, and navigation telemetry.
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found or stored result unavailable.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/export/csv" -O
```

---

### `GET /api/v1/analyses/{analysis_id}/export/geojson`
Exports geolocated targets from a completed survey analysis as an RFC 7946 GeoJSON `FeatureCollection`.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `application/geo+json`
- **Headers**:
  - `Content-Type`: `application/geo+json`
  - `Content-Disposition`: `attachment; filename="marinescan_{analysis_id}.geojson"`
- **Coordinate Convention**: Strict RFC 7946 compliance: Point coordinates are ordered `[longitude, latitude]` (NOT `[latitude, longitude]`).
- **Missing Coordinate Handling**: Ungeolocated targets or analyses without geographic fixes do not produce fake coordinates (never `0,0`); returns a valid empty `FeatureCollection` (`"features": []`).
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found or stored result unavailable.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/export/geojson" -O
```

---

### `GET /api/v1/analyses/{analysis_id}/export/track.geojson`
Exports the vessel/vehicle navigation acquisition track as an RFC 7946 GeoJSON `FeatureCollection` containing an ordered `LineString` geometry.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `application/geo+json`
- **Headers**:
  - `Content-Type`: `application/geo+json`
  - `Content-Disposition`: `attachment; filename="marinescan_{analysis_id}_track.geojson"`
- **Coordinate Convention**: Strict RFC 7946 compliance: Point coordinates are ordered `[longitude, latitude]` (NOT `[latitude, longitude]`).
- **Geometry Rules**:
  - $\ge 2$ valid navigation points: Emits a single `LineString` connecting sequential ping fixes in acquisition order.
  - Exactly 1 valid navigation point: Emits a `Point` geometry.
  - 0 valid navigation points: Emits an empty `FeatureCollection` (`"features": []`). Points with missing/null coordinates are excluded rather than plotted at `(0, 0)`.
- **Properties**: `analysis_id`, `source_format`, `total_pings`, `available_navigation_pings`, `start_timestamp`, `end_timestamp`.
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found, non-sonar analysis, or physical track artifact missing from storage.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/export/track.geojson" -O
```

---

### `GET /api/v1/analyses/{analysis_id}/export/track.csv`
Exports ping-by-ping telemetry and navigation track as a tabular CSV dataset in strict acquisition order.
- **Path Parameter**: `analysis_id` (string, e.g. `"msn_a1b2c3d4e5"`)
- **Response**: `200 OK` $\rightarrow$ `text/csv; charset=utf-8`
- **Headers**:
  - `Content-Type`: `text/csv; charset=utf-8`
  - `Content-Disposition`: `attachment; filename="marinescan_{analysis_id}_track.csv"`
- **Columns**: `analysis_id,ping_index,timestamp,latitude,longitude,heading,depth,altitude`
- **Missing Value Handling**: Unlogged/null fields rendered as empty strings (e.g. `,,`) — NEVER fabricated as `0.0`.
- **Error Responses**:
  - `404 Not Found`: Analysis ID not found, non-sonar analysis, or physical track artifact missing from storage.

#### Example Request (cURL)
```bash
curl -s "http://localhost:8000/api/v1/analyses/msn_a1b2c3d4e5/export/track.csv" -O
```

---

## 5. Detection Georeferencing & Geospatial Correlation (Phase 9)

In Phase 9, MarineScan correlates detections identified by YOLO on sonar waterfall rasters to the ping-level navigation track, calculates metric across-track offsets from the acoustic nadir, applies towfish layback if configured, and calculates deterministic WGS84 geographic target positions.

### `SonarTargetGeoreference` Schema

Each target detected on a raw sonar waterfall raster includes a `georeference` object within `MasterTargetResult`:

| Field | Type | Description |
|---|---|---|
| `status` | string | Correlation status: `"calculated"`, `"unavailable_missing_nav"`, or `"unavailable_missing_gsd"` |
| `coordinate_reference` | string | Geodetic datum reference (strictly `"WGS84"`) |
| `latitude` | float \| null | Calculated WGS84 latitude in decimal degrees |
| `longitude` | float \| null | Calculated WGS84 longitude in decimal degrees |
| `source_ping_index` | integer | Acquisition ping index in file corresponding to detection centroid |
| `waterfall_row` | integer | Waterfall raster scanline row corresponding to detection centroid (1:1 mapping) |
| `across_track_pixel` | float | Target centroid horizontal pixel coordinate in raster |
| `across_track_offset_m` | float \| null | Metric offset perpendicular to heading (+ starboard, - port) |
| `slant_range_m` | float \| null | Recorded slant range extent if available |
| `heading_deg` | float \| null | Sensor/vessel true heading in degrees used for projection |
| `layback_applied` | boolean | Whether towfish catenary layback correction was applied |
| `layback_distance_m` | float \| null | Horizontal layback distance in meters behind vessel if applied |
| `vessel_latitude` | float \| null | Surface vessel latitude at ping time |
| `vessel_longitude` | float \| null | Surface vessel longitude at ping time |
| `sensor_latitude` | float \| null | Towfish/sensor latitude at ping time |
| `sensor_longitude` | float \| null | Towfish/sensor longitude at ping time |
| `warnings` | string[] | Telemetry, resolution, or geometry correlation warnings |

### Georeferencing Principles & Safeguards
- **Zero Coordinate Fabrication**: If ping coordinates are unlogged or null, target coordinates strictly remain `null`. Coordinates `(0, 0)` or regional fallbacks are never generated.
- **GeoJSON Compliance**: Target features strictly follow RFC 7946 coordinate ordering `[longitude, latitude]`. Detections without coordinates are cleanly omitted from the FeatureCollection.
- **Backward Compatibility**: Conventional camera image uploads (JPEG/PNG/TIFF/BMP/WEBP) preserve standard vessel projection with `georeference=None`.

---

## 6. Physical Target Dimensions & Measurement (Phase 10)

Phase 10 introduces the dedicated `DimensionService` and enriches `MasterPhysicalDimensions` (`TargetDimensions`) with pixel extents, across-track/along-track metric resolutions, and measurement methodology status.

### `MasterPhysicalDimensions` Schema

| Field | Type | Description |
|---|---|---|
| `pixel_width` | float | Target bounding box width in pixels |
| `pixel_height` | float | Target bounding box height in pixels |
| `across_track_m` | float \| null | Real-world extent across-track in meters |
| `along_track_m` | float \| null | Real-world extent along-track in meters |
| `slant_range_m` | float \| null | Recorded or computed acoustic slant range (m) |
| `ground_range_m` | float \| null | Projected seabed horizontal distance from nadir (m) |
| `length_m` | float \| null | Longest physical dimension (m) |
| `width_m` | float \| null | Shortest physical dimension (m) |
| `height_m` | float \| null | Elevation off seabed from acoustic shadow or modeling (m) |
| `area_sq_m` | float \| null | Seabed contact footprint area (m²) |
| `estimated_volume_m3` | float \| null | Estimated 3D volumetric displacement (m³) |
| `dry_mass_metric_tons` | float \| null | Structural mass in air (metric tons) |
| `submerged_weight_kn` | float \| null | Underwater net weight in seawater (kN) |
| `recommended_crane_lift_tons` | float \| null | Salvage hoist requirement (1.5x dynamic safety) |
| `seabed_stability_index` | float \| null | Holding friction vs. bottom current drag force ratio |
| `seabed_mobility_status` | string \| null | Seabed stability category |
| `measurement_method` | string | `"sonar_raster_geometry"` or `"optical_camera_gsd"` |
| `measurement_status` | string | `"verified_complete"`, `"partial_across_only"`, or `"unavailable_missing_gsd"` |
| `warnings` | string[] | Dimensioning caveats, missing telemetry, or assumptions |

---

## 7. Maritime Risk Assessment & NOTMAR Directives (Phase 11)

Phase 11 enriches `TargetRiskAssessment` with Notice to Mariners (NOTMAR) decision logic, assessing collision hazard, draft clearance, and telemetry availability.

### NOTMAR Decision Logic & Status Values

| `notmar_status` | `notmar_required` | Criteria & Operational Directive |
|---|---|---|
| `RECOMMENDED` | `true` | Under-keel clearance $\le 3.5\text{ m}$ (or Critical risk) with verified geographic coordinates. Broadcast urgent NOTMAR with exact WGS84 location. |
| `UNKNOWN_INSUFFICIENT_DATA` | `false` | Shallow collision threat detected, but geographic coordinates are missing/unrecorded in raw file. Broadcast cannot issue specific location without fabrication. |
| `MONITOR` | `false` | Collision threat detected but target confidence is flagged as `SUSPECTED_FALSE_ALARM`. Secondary acoustic verification recommended before broadcast. |
| `NONE` | `false` | Safe water clearance maintained or biological marine biomass (`fish`). No broadcast warranted. |

---

## 8. Visual Annotation & Packaging (Phase 12)

Phase 12 delivers production visualization and hydrographic data packaging:
- **Visual Overlay (`render_detections_overlay`)**:
  - Color-coded bounding boxes by `RiskTier` (`CRITICAL` red `#E63946`, `HIGH` orange `#F4A261`, `MODERATE` amber `#E9C46A`, `LOW` teal `#2A9D8F`).
  - High-visibility badges displaying class, confidence, dimensions (e.g. `15.0x4.0m`), and `[GEO]` georeference indicators.
- **Hydrographic Data Exports**:
  - **GeoJSON**: RFC 7946 strictly ordered `[longitude, latitude]`; enriched feature properties with dimensions and NOTMAR directives.
  - **CSV**: Includes `pixel_width`, `pixel_height`, `across_track_m`, `along_track_m`, `notmar_status`, `notmar_required`, `notmar_reason`, etc.
  - **JSON**: Full backward-compatible package with all telemetry, dimensions, and risk fields.
