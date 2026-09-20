# MarineScan Live Demonstration & Evaluation Script

This script provides an end-to-end walkthrough for technical evaluators, marine surveyors, hydrographic researchers, and judges to experience the MarineScan subsea intelligence system on **macOS** and **Windows**.

---

## 1. Environment & System Startup

### Step 1: Start the Backend API Engine

#### macOS / Linux
Open Terminal 1:
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

#### Windows (PowerShell)
Open PowerShell Window 1:
```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

*Expected Terminal Log:*
```text
INFO:     Started server process
INFO:     Application startup complete.
INFO:     Model warmup complete on device: mps (or cuda / cpu)
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

### Step 2: Start the Frontend Dashboard

#### macOS / Linux / Windows
Open Terminal 2:
```bash
cd frontend
npm install
npm run dev
```

*Expected Terminal Log:*
```text
  VITE v5.x.x  ready in 240 ms
  ➜  Local:   http://localhost:8443/
```

---

## 2. Pre-Flight Verification & Diagnostics

Verify system connectivity and model readiness before presenting:

### A. Health & Model Architecture Inspection

#### macOS / Linux
```bash
curl -s http://localhost:8000/api/v1/health | jq
curl -s http://localhost:8000/api/v1/models/current | jq
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health" | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/models/current" | ConvertTo-Json
```

*Key Observations to Highlight:*
- Status: `"healthy"`
- Model Task: `"detect"`
- Model Architecture: `"yolo11"`
- Compute Device: `mps` (Apple Silicon Metal) or `cuda` (NVIDIA) or `cpu`
- Classes (7): `shipwreck`, `pipe`, `ghost_net`, `marine_debris`, `aircraft`, `other`, `fish`.

---

### B. Standalone YOLO11 Model Validation

Execute independent model inference to verify detection accuracy on real sonar imagery:

#### macOS / Linux
```bash
cd backend
./venv/bin/python test_yolo11_model.py "../frontend/public/accident.jpg" --conf 0.25 --iou 0.45 --imgsz 640
```

#### Windows (PowerShell)
```powershell
cd backend
.\venv\Scripts\python.exe test_yolo11_model.py "..\frontend\public\accident.jpg" --conf 0.25 --iou 0.45 --imgsz 640
```

*Output Files to Review:*
- `yolo11_validation_result.jpg`: Visual image with color-coded bounding boxes and confidence tags.
- `yolo11_validation_result.json`: Structured target list with normalized bounding coordinates.

---

### C. Standalone 12-Stage Intelligence Pipeline Runner

Execute the entire master intelligence pipeline directly from the command line:

#### macOS / Linux
```bash
python test_sonar.py sample_sidescan.png
```

#### Windows (PowerShell)
```powershell
python test_sonar.py sample_sidescan.png
```

*Terminal Output Features:*
- Complete ASCII telemetry table.
- Quality score, SNR, and contrast observations.
- Acoustic shadow ray vector calculations.
- Ocean physics: Mackenzie sound speed, 3D volume, submerged mass, 1.5× dynamic crane hoist ratings.
- WGS84 navigation coordinates and UTM positions.
- Maritime hazard score and USCG/IMO NOTMAR action advisories.
- Output image saved to `sonar_test_result.jpg`.

---

### D. Raw Sonar Recording Diagnostics (XTF & JSF)

Inspect raw sonar survey files and stream acoustic waterfall rasters without manual preprocessing:

#### macOS / Linux
```bash
# Diagnostic inspection of XTF survey header and channels:
cd backend
python -m app.sonar.inspect_xtf path/to/survey.xtf

# Diagnostic inspection of EdgeTech JSF packets:
python -m app.sonar.inspect_jsf path/to/survey.jsf

# Quick REST API header inspection:
curl -X POST "http://localhost:8000/api/v1/sonar/inspect" -F "file=@path/to/survey.xtf" | jq
```

#### Windows (PowerShell)
```powershell
# Diagnostic inspection of XTF survey header and channels:
cd backend
python -m app.sonar.inspect_xtf path\to\survey.xtf

# Diagnostic inspection of EdgeTech JSF packets:
python -m app.sonar.inspect_jsf path\to\survey.jsf

# Quick REST API header inspection:
$form = @{ file = Get-Item "path\to\survey.xtf" }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/sonar/inspect" -Method Post -Form $form | ConvertTo-Json
```

*Highlights:*
- Instant header extraction without decoding full acoustic rasters.
- Verifies sample rates, channel layout, ping count, and valid navigation fixes.

---

## 3. Interactive Web Dashboard Walkthrough

Open **`http://localhost:8443`** in your browser.

```
+-------------------------------------------------------------------------+
| MarineScan Hydrographic Intelligence Platform                           |
| Status: SYSTEM READY (YOLO11 MPS/CUDA Active)                           |
+-------------------------------------------------------------------------+
| [Upload Sonar File]  | [Preset: Sonar Acoustic] | [Depth: 35.0m]        |
|-------------------------------------------------------------------------|
| [Sonar Waterfall Display]            | [Hydrographic Telemetry Panel]   |
|                                      | - Target: det_5618a0db           |
|  * Yellow highlight boxes            | - Class: shipwreck (High Risk)   |
|  * Cyan shadow polygons              | - Length: 42.5m | Width: 11.2m   |
|  * Yellow projection vectors         | - Seabed Height: 6.8m            |
|                                      | - Net Submerged Mass: 142.3 t    |
|                                      | - Dynamic Crane Rating: 213.5 t  |
|                                      | - Seabed Stability: 2.1 (Stable) |
|--------------------------------------| - Nav Clearance: 28.2m           |
| [Interactive Mission Map (Leaflet)]  | - Directives: Broadcast NOTMAR   |
|  * RFC 7946 GeoJSON target markers   +----------------------------------|
|  * Survey vessel track and towfish   | [Export PDF] | [Export GeoJSON]  |
+-------------------------------------------------------------------------+
```

### Flow 1: Uploading Imagery & Configuring Survey Mission
1. Drag and drop `frontend/public/accident.jpg`, `backend/sample_sidescan.png`, or a raw survey file (`.xtf` / `.jsf`) into the upload zone.
   - For raw sonar recordings, MarineScan automatically inspects headers, validates navigation fixes, and builds the normalized acoustic waterfall raster without external tooling.
2. In the **Survey Parameters** panel:
   - **Vessel Coordinates**: Latitude `24.8607° N`, Longitude `67.0011° E` (auto-populated if present in raw sonar navigation packets).
   - **Vessel Heading**: `45.0°` (North-East track).
   - **Water Depth**: `35.0 meters`.
   - **Ground Sampling Distance (GSD)**: `0.05 meters/pixel` ($5\text{ cm/px}$, auto-calibrated from slant range if available).
   - **Towfish Layback**: Cable payout `60.0m`, sensor depth `18.0m`.

### Flow 2: Acoustic Image Preprocessing
1. Toggle the **Enhancement Preset** dropdown:
   - Select **`sonar_acoustic`**: Demonstrates bilateral speckle smoothing with CLAHE in LAB luminance space.
   - Select **`turbid_water`**: Demonstrates aggressive contrast stretching for murky or high-turbidity optical feeds.
   - Select **`edge_enhance`**: Accentuates sharp metallic boundaries of hulls and subsea pipelines.
2. Notice the live Image Quality metrics (Focus Variance, Contrast, SNR dB, Quality Tier).

### Flow 3: AI Detections & Acoustic Shadow Corroboration
1. Click **"Run Analysis"** to trigger the 12-stage Master Pipeline.
2. Review detected targets on the canvas:
   - Class-specific colored bounding boxes (`shipwreck`, `pipe`, `ghost_net`, `marine_debris`, `aircraft`).
   - Cyan polygonal contours delineating the physical acoustic shadow.
   - Yellow directional vectors confirming rays point radially away from the center nadir track.
3. Explain the hydrographic formula for target height off the seafloor:
   $$h = \frac{L_{\text{shadow}} \times H_{\text{altitude}}}{R_{\text{slant}} + L_{\text{shadow}}}$$

### Flow 4: Ocean Physics & Salvage Engineering
1. Select a target (e.g. `shipwreck`) to open the **Target Telemetry Card**:
   - **3D Dimensions**: Metric Length, Width, and Shadow-Derived Height.
   - **Volumetric Displacement**: Derived using class compaction factors ($\phi = 0.65$ for shipwrecks).
   - **Submerged Underwater Mass**: Archimedes buoyancy calculation subtracting displaced seawater.
   - **Dynamic Salvage Crane Rating**: Displays the **1.5× dynamic safety factor** rating required for vessel hoist winches during swell.
   - **Hydrodynamic Seabed Stability Index**: Shows whether ocean bottom currents will slide the debris across the seafloor.

### Flow 5: Geolocation & Mission Map
1. Examine the **Mission Map**:
   - Towfish catenary layback is accurately plotted astern of the surface vessel.
   - Target coordinate is rendered as an RFC 7946 GeoJSON feature.
   - Shows Decimal Degrees, Nautical DMS (`24° 51' 38.5" N`), and UTM coordinates.

### Flow 6: Maritime Risk Directives & Official Advisories
1. Examine the **Risk & Directives** section:
   - Under-keel draft clearance is checked against vessel categories.
   - Directives compliant with USCG/IMO NOTMAR and IHO S-57 electronic navigational charting are generated.
   - For `ghost_net`, an ALDFG commercial trawl alert is issued.
   - For `pipe`, a 250m subsea anchoring exclusion zone is recommended.

### Flow 7: Report Generation & Export
1. Click **"Generate Report"** to export a publication-ready PDF or JSON document containing the complete hydrographic survey findings.

---

## 4. Key Talking Points for Judges & Evaluators

1. **Native Raw Sonar Ingestion (XTF & JSF)**: Ingests raw Triton (`.xtf`) and EdgeTech (`.jsf`) survey recordings directly. Automatically parses headers, pings, multi-channel acoustic samples, and navigation coordinates into normalized waterfall rasters.
2. **Beyond Pure Computer Vision**: Standard AI models hallucinate on noisy underwater sonar. MarineScan enforces **Acoustic Shadow Corroboration** and **Ocean Physics Validation** to verify that a target is truly a 3D physical object.
3. **Tripartite Confidence Fusion**: Dynamically balances AI softmax confidence ($45\%$), shadow and physical evidence ($35\%$), and local acoustic image quality ($20\%$).
4. **Cross-Platform Engineering**: Zero vendor lock-in. Optimized natively for Apple Silicon Metal Performance Shaders (`mps`) on macOS, NVIDIA CUDA on Windows/Linux, and multi-threaded CPU fallback.
5. **Complete Hydrographic Workflow**: Handles the entire mission lifecycle from raw waterfall ingestion, through physics and geodesy, to official NOTMAR maritime directives.
