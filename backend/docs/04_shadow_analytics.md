# Component Guide: Acoustic Shadow & 3D Height Analytics

The **Acoustic Shadow Service** ([`shadow_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/shadow_service.py)) extracts and analyzes acoustic shadows cast by debris to physically confirm 3D seabed relief and calculate true target height off the seafloor.

---

## The Physics of Acoustic Shadows

In sidescan sonar (SSS), acoustic pulses travel outward from the central nadir ground-track. When an acoustic pulse encounters a 3D object protruding from the seabed:
1. **Highlight**: The face of the object reflecting sound back to the sensor produces a bright, high-intensity return.
2. **Shadow**: The acoustic pulse cannot penetrate the object, creating a dead zone (acoustic shadow) behind it where no sound reflects back.

```
       Towfish / Sonar Sensor (Nadir Track)
                     │
                     ▼
          Acoustic Pulse Propagation
  ──────────────────────────────────────────►
            ┌─────────┐
            │ Target  │  ◄ Bright Acoustic Highlight
  ──────────┴─────────┴─────────────────────
                       ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  ◄ Dark Acoustic Shadow Zone
                      └─────────────────────┘
                        Shadow Length (L)
```

Without an acoustic shadow, a bright return is likely a 2D surface feature (e.g. sand ripple, gravel patch, biological noise) rather than a solid 3D obstacle.

---

## 6-Stage Shadow Analysis Engine

### 1. Local Search ROI Extraction
- Crops a local Region of Interest (ROI) around the target highlight extending outward along the acoustic propagation ray.
- Computes local ambient seabed statistics ($\mu_{\text{seabed}}, \sigma_{\text{seabed}}$).
- Identifies dark pixels using adaptive background thresholding:
  $$\text{Threshold} = \max(12, \mu_{\text{seabed}} - 1.2 \times \sigma_{\text{seabed}})$$
- Applies morphological closing ($3 \times 3$ ellipse kernel) to eliminate isolated sensor noise spikes.

### 2. Spatial Relationship & Adjacency
- Computes centroid displacement $(\Delta x, \Delta y)$ between highlight and shadow candidate.
- Calculates boundary gap distance (in pixels and meters).
- Enforces strict proximity: a true acoustic shadow must touch or be immediately adjacent to the highlight boundary.

### 3. Directional Analysis & Nadir Alignment
- Computes the shadow propagation angle:
  $$\theta = \operatorname{atan2}(\Delta y, \Delta x) \in [0^\circ, 360^\circ)$$
- Compares against expected nadir-relative angle:
  - Starboard channel (right of nadir): shadow must propagate East ($0^\circ$).
  - Port channel (left of nadir): shadow must propagate West ($180^\circ$).
- Directional alignment score:
  $$S_{\text{direction}} = \max(0.0, \cos(\theta - \theta_{\text{expected}}))$$

### 4. Geometric Extent & 3D Height Formula
- Extracts oriented shadow length along ray ($L_{\text{shadow}}$) and width perpendicular to ray ($W_{\text{shadow}}$).
- Calculates the true physical elevation of the target off the seabed using the standard hydrographic shadow equation:
  $$h = \frac{L_{\text{shadow}} \times H_{\text{altitude}}}{R_{\text{slant}} + L_{\text{shadow}}}$$
  where:
  - $h$: Target height off seabed (m)
  - $L_{\text{shadow}}$: Physical length of acoustic shadow (m)
  - $H_{\text{altitude}}$: Sensor altitude above seafloor (m)
  - $R_{\text{slant}}$: Target slant range from sensor (m)

### 5. Multi-Factor Composite Shadow Score
- Evaluates 4 physical factors into a composite score in $[0.0, 1.0]$:
  $$S_{\text{shadow}} = 0.35 \cdot S_{\text{contrast}} + 0.30 \cdot S_{\text{adjacency}} + 0.25 \cdot S_{\text{direction}} + 0.10 \cdot S_{\text{geometry}}$$

### 6. Visual Overlay Rendering
- Overlays cyan polygons (`#00FFFF`) delineating detected shadow regions.
- Draws yellow directional vectors with arrowheads indicating acoustic projection paths.

---

## API Endpoints

- **`POST /api/v1/shadows/analyze`**: Extract acoustic shadows, directional metrics, and 3D height off seabed.
- **`POST /api/v1/shadows/visualize`**: Stream an annotated image with cyan shadow contours and yellow projection vectors.
