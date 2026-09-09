# Component Guide: Neural Inference Engine & High-Res Tiling

The **Inference Engine** ([`inference_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/inference_service.py)) provides hardware-accelerated computer vision for underwater target detection, sliding-window tiling, and metric dimension calculations.

---

## Technical Architecture

### 1. Model Architecture & Device Support
- **Model**: Ultralytics YOLO11 (`weights/yolo11_sonar_best.pt`, 5.20 MB).
- **7-Class Taxonomy**:
  - `0` — `shipwreck` (High risk: sunken vessels, navigational obstructions)
  - `1` — `pipe` (High risk: subsea oil/gas pipelines, tubular conduit, snag hazard)
  - `2` — `ghost_net` (Critical risk: abandoned/lost fishing gear, drifting netting, propeller hazard)
  - `3` — `marine_debris` (Moderate risk: discarded cargo, drums, anthropogenic plastics)
  - `4` — `aircraft` (Critical risk: downed airframes, fuselage sections, flight hazards)
  - `5` — `other` (Moderate risk: unclassified acoustic anomalies)
  - `6` — `fish` (Low risk: biological marine fauna, non-hazardous)

- **Device Loader** ([`model_loader.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/ml/model_loader.py)):
  - Thread-safe singleton with hot-reloading support.
  - Automatic hardware detection across platforms:
    - **macOS**: Apple Silicon GPU via Metal Performance Shaders (`mps`).
    - **Windows / Linux**: NVIDIA GPU via CUDA (`cuda`).
    - **Fallback**: CPU with OpenMP multi-threading (`cpu`).
  - Cold-start warm-up inference to eliminate initial request latency spikes.

---

## High-Resolution Sliding-Window Tiling (`predict_tiled`)

Sidescan sonar waterfall files often have extreme aspect ratios (e.g. $700 \times 10,000\text{px}$). Resizing such files directly to standard $640 \times 640$ model input dimensions destroys small targets.

```
       Original Sonar Waterfall (e.g. 700 x 2048)
 ┌──────────────────────────────────────────────────┐
 │                                                  │
 └──────────────────────────────────────────────────┘
            ↓ Sliced into Overlapping Tiles
 ┌─────────┬─────────┬─────────┬─────────┬──────────┐
 │ Tile 1  │ Tile 2  │ Tile 3  │ Tile 4  │  Tile 5  │
 └─────────┴─────────┴─────────┴─────────┴──────────┘
            ↓ Batched Neural Inference on GPU (MPS/CUDA)
            ↓ Local Box Translation to Global Image Space
            ↓ Global Non-Maximum Suppression (NMS)
 ┌──────────────────────────────────────────────────┐
 │   [Target A]                [Target B]           │
 └──────────────────────────────────────────────────┘
```

1. **Sliding Window Generation**:
   - Slices canvas into square tiles of dimension `tile_size` (default $640\text{px}$) with an `overlap_ratio` (default $0.25$, step $= 480\text{px}$).
   - Pads edge tiles smaller than `tile_size` with zero-value pixels to maintain clean tensor geometries.
   - Guaranteed full-width and full-height coverage including right and bottom boundary edges.
2. **Batched GPU Execution**:
   - Sends all tiles in a single batched tensor to the GPU.
3. **Global Coordinate Mapping**:
   - Adds tile offsets $(o_x, o_y)$ to local box predictions $(x_1, y_1, x_2, y_2)$ to restore global coordinates.
4. **Global NMS Suppression**:
   - Executes `cv2.dnn.NMSBoxes` across all tiles using `iou_merge_threshold` (default $0.40$) to seamlessly merge targets spanning across tile boundaries.

---

## Physical Metric Dimension Scaling

When the sensor Ground Sampling Distance (`meters_per_pixel`) is supplied:
- $\text{Length (meters)} = \max(\text{width}_{\text{px}}, \text{height}_{\text{px}}) \times \text{GSD}$
- $\text{Width (meters)} = \min(\text{width}_{\text{px}}, \text{height}_{\text{px}}) \times \text{GSD}$
- $\text{Seabed Contact Area (m}^2) = \text{Length} \times \text{Width}$

---

## Standalone Model Validation (`test_yolo11_model.py`)

Verify model performance on test imagery independently of the 12-stage pipeline:

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

---

## REST API Endpoints & Cross-Platform Invocations

- **`POST /api/v1/detections/predict`**: Single image detection with optional preprocessing, GSD scaling, and sliding-window tiling.
- **`POST /api/v1/detections/predict-batch`**: Parallel batched detection across multiple image files.
- **`POST /api/v1/detections/visualize`**: Direct binary JPEG render with color-coded bounding boxes and semi-transparent badges.

### Example Request: Single Image Detection

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/detections/predict" \
  -F "file=@sample_sidescan.png" \
  -F "confidence_threshold=0.25" \
  -F "meters_per_pixel=0.05"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "sample_sidescan.png"
    confidence_threshold = "0.25"
    meters_per_pixel = "0.05"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/detections/predict" -Method Post -Form $form
```
