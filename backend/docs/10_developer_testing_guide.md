# Component Guide: Developer & Testing Guide

This guide describes how to run automated tests, execute CLI diagnostic tools, write new test cases, and deploy the MarineScan backend.

---

## 1. Running Automated Tests

The test suite covers **81 automated test cases** across all 9 test modules with $100\%$ pass rates.

### Run All 81 Tests
```bash
cd backend
source venv/bin/activate
python -m unittest discover -s app/tests -p "test_*.py" -v
```

### Run Individual Test Suites
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

# 7. YOLO Neural Inference & Tiling Tests (8 tests)
python -m unittest app.tests.test_inference -v

# 8. Acoustic Preprocessing & CLAHE Tests (13 tests)
python -m unittest app.tests.test_preprocessing -v

# 9. Health & Model Management API Tests (12 tests)
python -m unittest app.tests.test_api -v
```

---

## 2. Command Line Diagnostic Runners

### Standalone CLI Pipeline Runner (`test_sonar.py`)
Run the entire 12-stage pipeline on any sonar image file from the terminal without starting a server:
```bash
# Run on real sidescan benchmark image:
python test_sonar.py sample_sidescan.png

# Or run without arguments to auto-generate a synthetic acoustic target:
python test_sonar.py
```
Outputs a detailed ASCII summary table of quality metrics, detections, shadows, physics, coordinates, and risk advisories, and saves the annotated visual image to `sonar_test_result.jpg`.

---

## 3. Fast Syntax & Bytecode Compilation Check

To verify all Python files compile cleanly with zero syntax errors or broken imports:
```bash
python -m compileall app
```

---

## 4. Writing New Tests (Best Practices)

When creating new test cases in `backend/app/tests/`:
1. **FastAPI Lifespan Context**: Use `cls._client_context = TestClient(app)` and `cls.client = cls._client_context.__enter__()` inside `setUpClass` to trigger FastAPI's `@asynccontextmanager` startup routines.
2. **Synthetic Image Fixtures**: Generate small synthetic NumPy arrays (`cv2.imencode('.jpg', ...)`) to keep unit tests fast ($< 0.1\text{s}$ per test).
3. **Pydantic Validation**: Assert against both parsed response attributes and raw JSON payloads.

---

## 5. Deployment with Uvicorn / Gunicorn

For production environments:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```
For containerized Docker deployment, ensure OpenCV headless dependencies (`libgl1-mesa-glx`, `libglib2.0-0`) are installed in the base image.
