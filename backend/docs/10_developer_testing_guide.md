# Component Guide: Developer & Testing Guide

This guide describes how to run automated test suites, execute standalone diagnostic scripts, write new test cases, and deploy the MarineScan backend on **macOS / Linux** and **Windows**.

---

## 1. Running Automated Tests

The automated test suite covers **163 test cases** across 15 test modules (160 passed, 3 expected skips due to pending real-world survey files, 0 failures, 0 errors).

### Run All 163 Tests

#### macOS / Linux
```bash
cd backend
source venv/bin/activate
python -m unittest discover -s app/tests -p "test_*.py" -v
```

#### Windows (PowerShell)
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python -m unittest discover -s app/tests -p "test_*.py" -v
```

#### Windows (Command Prompt `cmd.exe`)
```cmd
cd backend
venv\Scripts\activate.bat
python -m unittest discover -s app/tests -p "test_*.py" -v
```

---

### Run Individual Test Suites

#### macOS / Linux
```bash
# 1. Master Pipeline End-to-End Tests (6 tests)
python -m unittest app.tests.test_master_pipeline -v

# 2. Maritime Risk & NOTMAR Tests (8 tests)
python -m unittest app.tests.test_risk -v

# 3. Geolocation & Catenary Layback Tests (9 tests)
python -m unittest app.tests.test_geolocation -v

# 4. Multi-Source Confidence Calibration Tests (7 tests)
python -m unittest app.tests.test_confidence -v

# 5. Ocean Physics & Salvage Crane Tests (9 tests)
python -m unittest app.tests.test_physics -v

# 6. Acoustic Shadow Analytics Tests (9 tests)
python -m unittest app.tests.test_shadow -v

# 7. YOLO11 Neural Inference & Model Verification Tests (10 tests)
python -m unittest app.tests.test_inference -v

# 8. Acoustic Preprocessing & CLAHE Tests (13 tests)
python -m unittest app.tests.test_preprocessing -v

# 9. Health & Model Management API Tests (12 tests)
python -m unittest app.tests.test_api -v

# 10. Triton XTF Sonar Parser Tests (11 tests)
python -m unittest app.tests.test_xtf_parser -v

# 11. EdgeTech JSF Sonar Parser Tests (11 tests)
python -m unittest app.tests.test_jsf_parser -v

# 12. Acoustic Waterfall Raster Tests (16 tests)
python -m unittest app.tests.test_sonar_raster -v

# 13. Sonar Base Schemas & Contracts (17 tests)
python -m unittest app.tests.test_sonar_base -v

# 14. Sonar Inspection & Raster API Tests (11 tests)
python -m unittest app.tests.test_sonar_api -v

# 15. Raw Sonar End-to-End Pipeline Integration Tests (14 tests)
python -m unittest app.tests.test_sonar_pipeline_integration -v
```

#### Windows (PowerShell / CMD)
```powershell
# 1. Master Pipeline End-to-End Tests (6 tests)
python -m unittest app.tests.test_master_pipeline -v

# 2. Maritime Risk & NOTMAR Tests (8 tests)
python -m unittest app.tests.test_risk -v

# 3. Geolocation & Catenary Layback Tests (9 tests)
python -m unittest app.tests.test_geolocation -v

# 4. Multi-Source Confidence Calibration Tests (7 tests)
python -m unittest app.tests.test_confidence -v

# 5. Ocean Physics & Salvage Crane Tests (9 tests)
python -m unittest app.tests.test_physics -v

# 6. Acoustic Shadow Analytics Tests (9 tests)
python -m unittest app.tests.test_shadow -v

# 7. YOLO11 Neural Inference & Model Verification Tests (10 tests)
python -m unittest app.tests.test_inference -v

# 8. Acoustic Preprocessing & CLAHE Tests (13 tests)
python -m unittest app.tests.test_preprocessing -v

# 9. Health & Model Management API Tests (12 tests)
python -m unittest app.tests.test_api -v

# 10. Triton XTF Sonar Parser Tests (11 tests)
python -m unittest app.tests.test_xtf_parser -v

# 11. EdgeTech JSF Sonar Parser Tests (11 tests)
python -m unittest app.tests.test_jsf_parser -v

# 12. Acoustic Waterfall Raster Tests (16 tests)
python -m unittest app.tests.test_sonar_raster -v

# 13. Sonar Base Schemas & Contracts (17 tests)
python -m unittest app.tests.test_sonar_base -v

# 14. Sonar Inspection & Raster API Tests (11 tests)
python -m unittest app.tests.test_sonar_api -v

# 15. Raw Sonar End-to-End Pipeline Integration Tests (14 tests)
python -m unittest app.tests.test_sonar_pipeline_integration -v
```

## 2. Command Line Diagnostic Runners

### A. Model Accuracy & Benchmark Evaluation (`evaluate_accuracy.py`)
Calculates detection accuracy metrics (mAP@50, mAP@50-95, Precision, Recall) using ground truth datasets, or benchmarks latency, throughput (FPS), and confidence distribution across images:

#### macOS / Linux
```bash
# Benchmark on single image or folder:
cd backend
./venv/bin/python evaluate_accuracy.py --source "../frontend/public/accident.jpg"

# Full dataset accuracy evaluation (mAP, P, R):
./venv/bin/python evaluate_accuracy.py --data "../ml/configs/marine_debris.yaml" --split val
```

#### Windows (PowerShell)
```powershell
# Benchmark on single image or folder:
cd backend
.\venv\Scripts\python.exe evaluate_accuracy.py --source "..\frontend\public\accident.jpg"

# Full dataset accuracy evaluation (mAP, P, R):
.\venv\Scripts\python.exe evaluate_accuracy.py --data "..\ml\configs\marine_debris.yaml" --split val
```

#### Windows (Command Prompt `cmd.exe`)
```cmd
cd backend
venv\Scripts\python.exe evaluate_accuracy.py --source "..\frontend\public\accident.jpg"
venv\Scripts\python.exe evaluate_accuracy.py --data "..\ml\configs\marine_debris.yaml" --split val
```

**Outputs Produced**:
- Live ASCII terminal summary table of per-class Precision, Recall, and mAP.
- `accuracy_report.json`: Machine-readable performance and accuracy JSON report.

---

### B. Independent YOLO11 Model Validation (`test_yolo11_model.py`)
Performs model-only inference on any sidescan sonar or ROV image without invoking the 12-stage master pipeline (no preprocessing, shadow analysis, or physics checks).

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

#### Windows (Command Prompt `cmd.exe`)
```cmd
cd backend
venv\Scripts\python.exe test_yolo11_model.py "..\frontend\public\accident.jpg" --conf 0.25 --iou 0.45 --imgsz 640
```

**Outputs Produced**:
- `yolo11_validation_result.jpg`: Annotated detection image with class bounding boxes and confidence badges.
- `yolo11_validation_result.json`: Machine-readable JSON summary of classes, coordinates, and model metadata.

---

### C. Standalone 12-Stage CLI Pipeline Runner (`test_sonar.py`)
Executes the full 12-stage intelligence pipeline on an image from the terminal with live ASCII telemetry:

#### macOS / Linux
```bash
# Run on real sidescan benchmark image:
python test_sonar.py sample_sidescan.png

# Or run without arguments to auto-generate a synthetic acoustic target:
python test_sonar.py
```

#### Windows (PowerShell / CMD)
```powershell
# Run on real sidescan benchmark image:
python test_sonar.py sample_sidescan.png

# Or run without arguments to auto-generate a synthetic acoustic target:
python test_sonar.py
```

**Output**:
- Comprehensive ASCII summary table (Image Quality, Detections, Acoustic Shadows, Ocean Physics, Geolocation, Maritime Risk Directives).
- Saves full visual overlay to `sonar_test_result.jpg`.

---

### D. Standalone Sonar Survey Inspection Utilities (`inspect_xtf.py` & `inspect_jsf.py`)
Inspect raw survey recordings directly from the terminal to evaluate packet structure, ping count, sample channels, and navigation fixes without launching the full web server:

#### macOS / Linux
```bash
cd backend
# Inspect Triton XTF survey recording:
python -m app.sonar.inspect_xtf path/to/survey.xtf

# Inspect EdgeTech JSF survey recording:
python -m app.sonar.inspect_jsf path/to/survey.jsf
```

#### Windows (PowerShell / CMD)
```powershell
cd backend
# Inspect Triton XTF survey recording:
python -m app.sonar.inspect_xtf path\to\survey.xtf

# Inspect EdgeTech JSF survey recording:
python -m app.sonar.inspect_jsf path\to\survey.jsf
```

**Output**:
- File format, header sizes, sonar frequencies, and sample rate.
- Port / Starboard channel layout and max sample lengths.
- Ping count and along-track duration.
- Geodetic bounding box and representative GPS fix.

---

## 3. Fast Syntax & Bytecode Compilation Check

To verify all Python files compile cleanly across platforms with zero syntax errors or broken imports:

#### macOS / Linux
```bash
python3 -m compileall app
```

#### Windows (PowerShell / CMD)
```powershell
python -m compileall app
```

---

## 4. Writing New Tests (Best Practices)

When creating new test cases in `backend/app/tests/`:
1. **FastAPI Lifespan Context**: Use `cls._client_context = TestClient(app)` and `cls.client = cls._client_context.__enter__()` inside `setUpClass` to trigger FastAPI's `@asynccontextmanager` startup routines.
2. **Synthetic Image Fixtures**: Generate small synthetic NumPy arrays (`cv2.imencode('.jpg', ...)`) to keep unit tests fast ($< 0.1\text{s}$ per test).
3. **Pydantic Validation**: Assert against both parsed response attributes and raw JSON payloads.
4. **Cross-Platform Paths**: Always use `pathlib.Path` or `os.path.join()` rather than hardcoded `/` or `\` to ensure tests pass on both POSIX and Windows.

---

## 5. Development and Production Server Deployment

### Development Server (Auto-Reload)

#### macOS / Linux
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

#### Windows (PowerShell)
```powershell
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

#### Windows (Command Prompt `cmd.exe`)
```cmd
cd backend
venv\Scripts\activate.bat
uvicorn app.main:app --reload --port 8000
```

### Production Deployment

#### macOS / Linux (Uvicorn Multi-Worker)
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### Windows (Uvicorn Multi-Worker)
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

*Note: For containerized Docker deployment, ensure OpenCV headless dependencies (`libgl1-mesa-glx`, `libglib2.0-0`) are installed in the base image.*
