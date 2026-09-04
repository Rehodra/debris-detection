# MarineScan — Autonomous Marine Debris Detection & Hydrographic Intelligence

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-YOLOv8-EE4C2C.svg)](https://pytorch.org/)
[![Tests](https://img.shields.io/badge/tests-81%2F81%20passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

**MarineScan** is a subsea computer vision, acoustic shadow corroboration, ocean physics modeling, WGS84 geodesy, and maritime risk assessment platform for sidescan sonar (SSS) and ROV optical feeds.

---

## 12-Stage Master Pipeline

```
                 ┌───────────────┐
                 │ Uploaded File │
                 └───────┬───────┘
                         ↓
                 1. Input validation
                         ↓
                   2. Quality check
                         ↓
                   3. Preprocessing
                         ↓
                    4. YOLO11-Seg
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

## Documentation Navigation

The codebase is thoroughly documented to assist engineers, researchers, and frontend teams:

- **[Main Backend README](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/README.md)**: Full architecture, quickstart, directory structure, endpoint catalog.
- **Subsystem Component Guides**:
  1. **[12-Stage Master Pipeline](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/01_master_pipeline.md)**: End-to-end orchestration, `MasterAnalysisResult`, and latency telemetry.
  2. **[Acoustic Preprocessing Service](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/02_preprocessing_service.md)**: Speckle filtering, CLAHE in LAB space, gamma LUT, and false colormaps.
  3. **[Inference Engine & High-Res Tiling](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/03_inference_engine.md)**: Hardware-accelerated YOLOv8n, sliding-window tiling with Global NMS, physical metric scaling.
  4. **[Acoustic Shadow & 3D Height Analytics](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/04_shadow_analytics.md)**: Highlight-shadow extraction, nadir ray alignment, and hydrographic seabed elevation formula.
  5. **[Ocean Physics & Salvage Engineering](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/05_physics_engine.md)**: Mackenzie sound speed, 3D volume, submerged mass, 1.5× crane hoist ratings, and hydrodynamic seabed stability.
  6. **[Confidence Calibration & Explainability](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/06_confidence_calibration.md)**: Multi-pillar fusion (AI + Physics + Quality), dynamic gating, operational trust tiers, plain-language notes.
  7. **[Geolocation, Towfish Layback & Mapping](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/07_geolocation_service.md)**: WGS84 ellipsoidal geodesy, catenary towfish layback, gyro rotation, Nautical DMS, UTM, RFC 7946 GeoJSON.
  8. **[Maritime Risk Assessment & NOTMAR Directives](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/08_maritime_risk_service.md)**: Under-keel draft clearance, trawl snag risk, pipeline threat, USCG/IMO NOTMAR advisories.
  9. **[Complete API Reference (25 Endpoints)](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/09_api_reference.md)**: All REST endpoints, schemas, parameters, and curl examples.
  10. **[Developer & Testing Guide](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/docs/10_developer_testing_guide.md)**: Running all 81 automated tests, `test_sonar.py` CLI runner, deployment instructions.

---

## Quickstart

```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## Test Verification

Run all **81 automated tests**:
```bash
cd backend
source venv/bin/activate
python -m unittest discover -s app/tests -p "test_*.py" -v
```
*(81 tests pass with 100% success in ~4.2 seconds)*
