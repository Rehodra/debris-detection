# MarineScan — Autonomous Marine Debris Detection & Hydrographic Intelligence

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-YOLO11%20%7C%20MPS%20%7C%20CUDA-EE4C2C.svg)](https://pytorch.org/)
[![Tests](https://img.shields.io/badge/tests-160%2F163%20passing%20(3%20skips)-brightgreen.svg)]()
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**MarineScan** is an autonomous subsea computer vision, acoustic shadow corroboration, ocean physics modeling, WGS84 geodesy, and maritime risk assessment platform. It natively ingests raw sidescan sonar survey recordings (**`.xtf`**, **`.jsf`**) and high-resolution optical/acoustic imagery (**JPEG**, **PNG**, **TIFF**, **BMP**, **WEBP**).

---

## 7-Class Marine Detection Taxonomy

MarineScan detects and evaluates 7 distinct subsea target classes using a fine-tuned **YOLO11** model:

| ID | Class Name | Category | Risk Level | Description |
|:---:|:---|:---|:---:|:---|
| `0` | **`shipwreck`** | Maritime Vessel | **High** | Sunken hulls, superstructures, and navigational obstructions |
| `1` | **`pipe`** | Subsea Infrastructure | **High** | Subsea oil/gas pipelines, tubular conduit, snag hazards |
| `2` | **`ghost_net`** | Abandoned Fishing Gear | **Critical** | ALDFG gear, drifting nets, severe wildlife & propeller snagging |
| `3` | **`marine_debris`** | Anthropogenic Waste | **Moderate** | Discarded shipping containers, oil drums, seafloor waste |
| `4` | **`aircraft`** | Aerospace Wreckage | **Critical** | Downed airframes, fuselage sections, flight equipment |
| `5` | **`other`** | Unclassified Target | **Moderate** | Unidentified seafloor acoustic reflector / anomaly |
| `6` | **`fish`** | Marine Fauna | **Low** | Biological marine life, fish schools (non-hazardous) |

---

## 12-Stage Master Intelligence Pipeline

```
                 ┌──────────────────────────────────────┐
                 │ Raw Sonar (.xtf / .jsf) or Image File │
                 └──────────────────┬───────────────────┘
                                    ↓
                 1. Input Validation & Sonar Ingestion
                    (XTF/JSF -> Waterfall Raster -> BGR)
                                    ↓
                           2. Quality Check
                                    ↓
                           3. Preprocessing
                                    ↓
                         4. YOLO11 Inference
                                    ↓
                          5. Candidate List
                                    ↓
                         6. Shadow Evidence
                                    ↓
                        7. Physics Validation
                                    ↓
                        8. Confidence Fusion
                                    ↓
                           9. Geolocation
                                    ↓
                         10. Dimension Estimate
                                    ↓
                         11. Risk Classification
                                    ↓
                       12. Compiled Intelligence
```

---

## Quickstart Guide (macOS & Windows)

### 1. Backend Setup

#### macOS / Linux
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Windows (PowerShell)
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Windows (Command Prompt `cmd.exe`)
```cmd
cd backend
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### 2. Frontend Setup

#### macOS / Linux / Windows
```bash
cd frontend
npm install
npm run dev
```
- **Web Application**: [http://localhost:8443](http://localhost:8443) (or assigned Vite port)

---

## Model-Only Validation Script

Run independent inference on any sonar image without invoking the full master pipeline:

#### macOS / Linux
```bash
cd backend
./venv/bin/python test_yolo11_model.py "../frontend/public/accident.jpg" --conf 0.25 --iou 0.45 --imgsz 640
```

#### Windows (PowerShell / CMD)
```powershell
cd backend
.\venv\Scripts\python.exe test_yolo11_model.py "..\frontend\public\accident.jpg" --conf 0.25 --iou 0.45 --imgsz 640
```

Outputs:
- Annotated Image: `yolo11_validation_result.jpg`
- Structured JSON Report: `yolo11_validation_result.json`

---

## Model Accuracy & Benchmark Evaluation Script

Evaluate mAP@50, mAP@50-95, precision, recall, and detection speed across datasets or image folders:

#### macOS / Linux
```bash
# Benchmark on an image or directory:
cd backend
./venv/bin/python evaluate_accuracy.py --source "../frontend/public/accident.jpg"

# Full ground truth validation (if dataset.yaml available):
./venv/bin/python evaluate_accuracy.py --data "../ml/configs/marine_debris.yaml" --split val
```

#### Windows (PowerShell / CMD)
```powershell
# Benchmark on an image or directory:
cd backend
.\venv\Scripts\python.exe evaluate_accuracy.py --source "..\frontend\public\accident.jpg"

# Full ground truth validation (if dataset.yaml available):
.\venv\Scripts\python.exe evaluate_accuracy.py --data "..\ml\configs\marine_debris.yaml" --split val
```

---

## Test Verification

Run all **163 automated tests** across all 15 test suites:

#### macOS / Linux
```bash
cd backend
source venv/bin/activate
python -m unittest discover -s app/tests -p "test_*.py" -v
```

#### Windows (PowerShell / CMD)
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m unittest discover -s app/tests -p "test_*.py" -v
```
*(160 tests pass, 3 expected skips due to pending real-world field survey recordings, 0 failures, 0 errors)*

---

## Subsystem Documentation Navigation

Detailed guides are located in [`backend/docs/`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/):
1. **[12-Stage Master Pipeline](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/01_master_pipeline.md)**: End-to-end orchestration, `MasterAnalysisResult`, and telemetry.
2. **[Acoustic Preprocessing Service](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/02_preprocessing_service.md)**: Speckle filtering, CLAHE in LAB space, gamma LUT, false colormaps.
3. **[Inference Engine & High-Res Tiling](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/03_inference_engine.md)**: YOLO11 acceleration (MPS/CUDA/CPU), sliding-window tiling, Global NMS.
4. **[Acoustic Shadow & 3D Height Analytics](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/04_shadow_analytics.md)**: Nadir ray alignment and hydrographic elevation formula.
5. **[Ocean Physics & Salvage Engineering](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/05_physics_engine.md)**: Mackenzie sound speed, 3D volume, submerged mass, 1.5× crane hoist ratings, seabed stability.
6. **[Confidence Calibration & Explainability](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/06_confidence_calibration.md)**: Multi-pillar fusion (AI + Physics + Quality), dynamic gating, 4 trust tiers.
7. **[Geolocation, Towfish Layback & Mapping](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/07_geolocation_service.md)**: WGS84 geodesy, catenary towfish layback, gyro rotation, UTM, RFC 7946 GeoJSON.
8. **[Maritime Risk Assessment & NOTMAR Directives](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/08_maritime_risk_service.md)**: Under-keel draft clearance, trawl snag risk, pipeline threat, USCG/IMO NOTMAR advisories.
9. **[Complete API Reference (28 Endpoints)](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/09_api_reference.md)**: All REST endpoints, schemas, parameters, and curl examples.
10. **[Developer & Testing Guide](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/10_developer_testing_guide.md)**: Running all 163 tests, validation runners, cross-platform deployment.
11. **[Raw Sonar Ingestion Engine (.xtf / .jsf)](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/11_raw_sonar_ingestion.md)**: XTF and EdgeTech JSF binary parsing, normalized waterfall rasters, and pipeline integration.

