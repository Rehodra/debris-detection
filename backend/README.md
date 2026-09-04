# MarineScan Debris Detection — Backend & Analytics Engine

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-YOLOv8%20%7C%20MPS%20%7C%20CUDA-EE4C2C.svg)](https://pytorch.org/)
[![Tests](https://img.shields.io/badge/tests-81%2F81%20passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

Production-grade subsea computer vision, acoustic shadow corroboration, ocean physics modeling, WGS84 geodesy, and maritime risk assessment engine for sidescan sonar (SSS) and ROV optical imagery.

---

## Architecture Overview

The backend is architected around an autonomous **12-Stage Master Intelligence Pipeline** that transforms raw sonar waterfall files into geolocated, physically validated, and risk-classified marine intelligence reports:

```
                          ┌───────────────┐
                          │ Uploaded File │
                          └───────┬───────┘
                                  ↓
                        1. Input Validation
                                  ↓
                          2. Quality Check
                                  ↓
                          3. Preprocessing
                                  ↓
                        4. YOLO Detection
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
                       10. Dimension Scaling
                                  ↓
                       11. Risk Classification
                                  ↓
                         12. Final Result
```

---

## Modular Component Documentation

Every subsystem is documented in detail in the [`docs/`](./docs/) directory to assist engineers, researchers, and frontend teams:

| Module | Documentation Link | Key Responsibilities |
|---|---|---|
| **Master Pipeline** | [`docs/01_master_pipeline.md`](./docs/01_master_pipeline.md) | End-to-end 12-stage orchestration, `MasterAnalysisResult`, latency telemetry |
| **Preprocessing** | [`docs/02_preprocessing_service.md`](./docs/02_preprocessing_service.md) | Bilateral/median filtering, CLAHE in LAB space, gamma LUT, false colormaps |
| **Inference Engine** | [`docs/03_inference_engine.md`](./docs/03_inference_engine.md) | YOLOv8n hardware acceleration, sliding-window tiling, Global NMS, GSD scaling |
| **Acoustic Shadows** | [`docs/04_shadow_analytics.md`](./docs/04_shadow_analytics.md) | Highlight-shadow extraction, nadir ray alignment, hydrographic 3D height off seabed |
| **Ocean Physics** | [`docs/05_physics_engine.md`](./docs/05_physics_engine.md) | Mackenzie sound speed, 3D volume, submerged mass, 1.5x crane hoist, seabed stability |
| **Confidence Fusion**| [`docs/06_confidence_calibration.md`](./docs/06_confidence_calibration.md) | Multi-pillar fusion (AI + Physics + Quality), dynamic gating, 4 trust tiers |
| **Geolocation** | [`docs/07_geolocation_service.md`](./docs/07_geolocation_service.md) | WGS84 geodesy, catenary towfish layback, gyro rotation, UTM, RFC 7946 GeoJSON |
| **Maritime Risk** | [`docs/08_maritime_risk_service.md`](./docs/08_maritime_risk_service.md) | Under-keel draft clearance, trawl snag risk, pipeline threats, USCG/IMO NOTMAR |
| **API Reference** | [`docs/09_api_reference.md`](./docs/09_api_reference.md) | Complete OpenAPI catalog of all 25 endpoints, parameter schemas, curl examples |
| **Testing Guide** | [`docs/10_developer_testing_guide.md`](./docs/10_developer_testing_guide.md) | Running 81 unit tests, `test_sonar.py` CLI runner, test writing guidelines |

---

## Directory Structure

```text
backend/
├── app/
│   ├── api/                    # API Route Handlers
│   │   └── v1/
│   │       ├── analyses.py      # Master Pipeline (/analyses)
│   │       ├── confidence.py    # Confidence Fusion (/confidence)
│   │       ├── detections.py    # YOLO Inference (/detections)
│   │       ├── geolocation.py   # Geodesy & Layback (/geolocation)
│   │       ├── health.py        # Health & System Status (/health)
│   │       ├── models.py        # Model Management (/models)
│   │       ├── physics.py       # Ocean Physics & Salvage (/physics)
│   │       ├── preprocessing.py # Denoising & CLAHE (/preprocessing)
│   │       ├── risk.py          # Maritime Hazard & NOTMAR (/risk)
│   │       ├── shadows.py       # Acoustic Shadows (/shadows)
│   │       └── __init__.py      # Router aggregation
│   ├── core/                    # App configuration & settings
│   │   └── config.py            # Pydantic Settings (env variables, thresholds)
│   ├── ml/                      # Machine Learning Integration
│   │   ├── class_map.py         # Classes, display names, hazard levels, colors
│   │   ├── model_loader.py      # Thread-safe model singleton with warm-up
│   │   ├── postprocess.py       # Box normalization & visual overlay rendering
│   │   └── weights/             # Ultralytics weights (best.pt)
│   ├── schemas/                 # Pydantic Data Contracts (Input/Output validation)
│   │   ├── analysis.py          # Master analysis & target schemas
│   │   ├── common.py            # Generic API & error responses
│   │   ├── confidence.py        # Trust tiers & multi-source fusion schemas
│   │   ├── detection.py         # Bounding boxes, image metadata, tiling config
│   │   ├── geolocation.py       # WGS84, DMS, UTM, GeoJSON FeatureCollections
│   │   ├── physics.py           # Volume, mass, buoyancy, stability schemas
│   │   ├── preprocessing.py     # Preset configs, colormaps, quality telemetry
│   │   ├── risk.py              # Under-keel clearance, risk factors, directives
│   │   └── shadow.py            # Shadow candidate, direction, extent schemas
│   ├── services/                # Pure Business Logic Layer
│   │   ├── confidence_service.py
│   │   ├── geolocation_service.py
│   │   ├── inference_service.py
│   │   ├── input_service.py
│   │   ├── master_pipeline_service.py
│   │   ├── physics_service.py
│   │   ├── preprocessing_service.py
│   │   ├── quality_service.py
│   │   ├── risk_service.py
│   │   └── shadow_service.py
│   └── tests/                   # Automated Unit & Integration Test Suites
│       ├── test_api.py
│       ├── test_confidence.py
│       ├── test_geolocation.py
│       ├── test_inference.py
│       ├── test_master_pipeline.py
│       ├── test_physics.py
│       ├── test_preprocessing.py
│       ├── test_risk.py
│       └── test_shadow.py
├── docs/                        # Subsystem Architectural Documentation
├── requirements.txt             # Python dependencies
├── sample_sidescan.png          # Real sidescan sonar benchmark image
├── test_sonar.py                # Standalone CLI test runner
└── test_pipeline.py             # Preprocessing + Inference verification CLI
```

---

## Quickstart Guide

### 1. Environment Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Start the FastAPI Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

- **Interactive API Documentation (Swagger UI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative Documentation (ReDoc)**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **API Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## Running Verification & Tests

### Automated Test Suite (81 Tests)
Execute all 81 automated tests across all 9 test suites:
```bash
python -m unittest discover -s app/tests -p "test_*.py" -v
```

### Standalone CLI Pipeline Runner
Test any sonar image file from the command line with full terminal telemetry and image output:
```bash
python test_sonar.py sample_sidescan.png
```
*(Annotated image output is saved to `sonar_test_result.jpg`)*

---

## Active API Endpoints (25 Endpoints)

| Router | Method | Endpoint | Description |
|---|---|---|---|
| **Master Analysis** | `POST` | `/api/v1/analyses/analyze` | Execute complete 12-stage Master Pipeline |
| | `POST` | `/api/v1/analyses/visualize` | Stream annotated JPEG with boxes and shadow rays |
| **Detections** | `POST` | `/api/v1/detections/predict` | Single-image YOLO inference with optional tiling |
| | `POST` | `/api/v1/detections/predict-batch` | Multi-image parallel batched detection |
| | `POST` | `/api/v1/detections/visualize` | Render detection boxes and confidence badges |
| **Preprocessing** | `GET` | `/api/v1/preprocessing/presets` | List all 6 enhancement presets |
| | `POST` | `/api/v1/preprocessing/process` | Apply custom denoising, CLAHE, gamma, and colormaps |
| | `POST` | `/api/v1/preprocessing/preview` | Return enhanced image binary stream |
| **Shadows** | `POST` | `/api/v1/shadows/analyze` | Extract acoustic shadows and 3D height off seabed |
| | `POST` | `/api/v1/shadows/visualize` | Render cyan shadow polygons and yellow projection rays |
| **Physics** | `GET` | `/api/v1/physics/environment` | Calculate Mackenzie sound speed, absorption, wavelength |
| | `POST` | `/api/v1/physics/analyze-target` | Target volume, mass, crane hoist rating, stability |
| | `POST` | `/api/v1/physics/analyze-image` | End-to-end detection + physics enrichment |
| **Confidence** | `POST` | `/api/v1/confidence/evaluate-target` | Multi-pillar fusion & trust tier for single target |
| | `POST` | `/api/v1/confidence/analyze-image` | End-to-end detection + confidence calibration |
| **Geolocation** | `POST` | `/api/v1/geolocation/layback` | Calculate towfish position astern of surface ship |
| | `POST` | `/api/v1/geolocation/target` | Geolocate single pixel target to WGS84, DMS, UTM |
| | `POST` | `/api/v1/geolocation/analyze-image` | End-to-end detection + geolocation + GeoJSON export |
| **Maritime Risk** | `POST` | `/api/v1/risk/evaluate-target` | Evaluate navigational clearance, trawl risk, & NOTMAR |
| | `POST` | `/api/v1/risk/analyze-image` | End-to-end detection + clearance + risk scoring |
| **Models & Health** | `GET` | `/api/v1/models/current` | Active model architecture, device, and class list |
| | `GET` | `/api/v1/models/classes` | Class metadata, hazard tiers, and color tokens |
| | `POST` | `/api/v1/models/reload` | Hot-reload model weights from disk |
| | `GET` | `/api/v1/health` | Health check and device status |
| | `GET` | `/` | Root API service information |
