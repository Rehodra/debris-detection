# Component Guide: Acoustic Preprocessing Service

The **Preprocessing Service** ([`preprocessing_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/preprocessing_service.py)) enhances sonar backscatter and ROV optical imagery before feeding it to neural networks or human operators.

---

## Technical Capabilities

### 1. Acoustic Speckle Denoising
Sidescan sonar imagery suffers from multiplicative acoustic speckle noise caused by coherent interference of backscattered acoustic waves:
- **Bilateral Filtering**: Smooths speckle while preserving high-frequency edges of debris boundaries and shadow edges.
  ```python
  cv2.bilateralFilter(image, d=diameter, sigmaColor=sigma_color, sigmaSpace=sigma_space)
  ```
- **Median Filtering**: Highly effective for salt-and-pepper sensor dropouts.
- **Gaussian Filtering**: Rapid low-pass smoothing for fast survey passes.

### 2. CLAHE (Contrast-Limited Adaptive Histogram Equalization)
Standard histogram equalization blows out bright seabed returns and washes out subtle acoustic shadows. 
MarineScan performs CLAHE in the **CIE LAB color space**:
1. Converts BGR to LAB color space.
2. Applies CLAHE exclusively to the $L$ (Luminance) channel:
   ```python
   clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
   l_channel = clahe.apply(l_channel)
   ```
3. Recombines with unchanged $A$ and $B$ chrominance channels and converts back to BGR.
4. **Benefit**: Boosts local target-to-seabed contrast without distorting chromatic balances or amplifying background noise.

### 3. Fast Gamma Lookup-Table (LUT) Adjustment
Non-linear gamma adjustment compensates for deep-water attenuation or sensor over-amplification:
$$I_{\text{out}} = 255 \times \left(\frac{I_{\text{in}}}{255}\right)^\gamma$$
Implemented via a 256-element precomputed uint8 lookup table for sub-millisecond execution.

### 4. False-Color Sonar Colormaps
Translates single-channel or grayscale sonar backscatter into hydrographically optimized false-color palettes:
- `amber`: Classic sidescan sonar golden-brown palette (optimizes contrast for acoustic shadows).
- `inferno`: High-contrast black-to-yellow thermal gradient.
- `viridis`: Perceptually uniform scientific colormap.
- `ocean`: Deep blue to cyan marine palette.
- `bone`: Grayscale with subtle cyan tint.
- `jet`: Rainbow false-color display.

---

## Curated Presets

| Preset | Target Environment | Key Settings |
|---|---|---|
| `sonar_acoustic` | Standard sidescan sonar waterfalls | Bilateral denoise, CLAHE clip $2.5$, grid $8\times8$, gamma $1.0$ |
| `turbid_water` | Low-visibility, high-turbidity optical/sonar | Median denoise, aggressive CLAHE clip $4.0$, gamma $0.85$ |
| `balanced` | General-purpose balanced enhancement | Bilateral denoise, CLAHE clip $2.0$, unsharp mask sharpening |
| `edge_enhance` | Structural inspection (wreck frames, pipelines) | CLAHE clip $3.0$, unsharp masking kernel |
| `raw_normalize` | Pure min-max dynamic range stretching | Linear normalization to $[0, 255]$ without filtering |
| `fast` | Real-time high-frame-rate streaming | Fast Gaussian blur and gamma correction |

---

## API Endpoints

- **`GET /api/v1/preprocessing/presets`**: List all 6 presets and their configuration parameters.
- **`POST /api/v1/preprocessing/process`**: Process an image with custom settings or presets and return telemetry (SNR, dynamic range, contrast).
- **`POST /api/v1/preprocessing/preview`**: Process and stream directly the enhanced JPEG binary.
