# Component Guide: Ocean Physics, Hydrography & Salvage Engineering

The **Physics Service** ([`physics_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/physics_service.py)) calculates physical sound propagation, slant-to-ground range conversions, 3D volumetric displacement, dry/submerged mass, dynamic salvage crane hoist capacities, and seabed hydrodynamic stability.

---

## 1. Ocean Acoustics

### Mackenzie (1981) Speed of Sound in Seawater
Calculates the speed of sound $c(T, S, D)$ as a function of temperature ($T$ in $^\circ\text{C}$), salinity ($S$ in PSU), and depth ($D$ in meters):
$$c(T, S, D) \approx 1448.96 + 4.591T - 5.304 \times 10^{-2}T^2 + 2.374 \times 10^{-4}T^3 + 1.340(S - 35) + 1.630 \times 10^{-2}D + 1.675 \times 10^{-7}D^2 - 1.025 \times 10^{-2}T(S - 35) - 7.139 \times 10^{-13}TD^3$$

### Sonar Wavelength & High-Frequency Acoustic Absorption
- Acoustic wavelength: $\lambda = \frac{c}{f}$
- High-frequency absorption $\alpha(f)$ via Francois-Garrison formulation (viscous relaxation of water + chemical relaxation of boric acid and magnesium sulfate).

---

## 2. Sonar Geometry: Slant-to-Ground Range Conversion

Sidescan sonars measure time-of-flight, corresponding to the **slant range** ($R_s$) through the water column. To map targets to true horizontal distance on the seabed ($R_g$):
$$R_g = \sqrt{\max(0, R_s^2 - H_{\text{alt}}^2)}$$
$$\text{Grazing Angle: } \psi = \arcsin\left(\frac{H_{\text{alt}}}{R_s}\right)$$

---

## 3. 3D Volumetric Displacement & Structural Mass

Target dimensions (Length $L$, Width $W$, Height $H$) are scaled using class compaction factors calibrated for subsea structures:

| Class | Shape Compaction Factor ($\phi$) | Typical Bulk Density ($\rho$ in $\text{kg/m}^3$) | Description |
|---|---|---|---|
| `shipwreck` | $0.65$ | $1800.0$ | Sunken steel hull, machinery, cargo holds |
| `pipe` | $0.70$ | $7850.0$ | Subsea steel oil/gas pipeline, heavy tubular conduit |
| `ghost_net` | $0.25$ | $1150.0$ | Synthetic fishing gear polymer filaments in seawater |
| `marine_debris` | $0.50$ | $1350.0$ | Mixed plastic, metal drums, container fragments |
| `aircraft` | $0.35$ | $650.0$ | Hollow fuselage, wings, lightweight aluminum airframe |
| `other` | $0.50$ | $1400.0$ | Lost shipping containers, structural seafloor scrap |
| `fish` | $0.48$ | $1025.0$ | Neutrally buoyant marine biomass |

$$\text{Volume: } V = L \times W \times H \times \phi \quad (\text{m}^3)$$
$$\text{Dry Mass: } M_{\text{dry}} = \frac{V \times \rho_{\text{material}}}{1000.0} \quad (\text{metric tons})$$

---

## 4. Archimedes Buoyancy & Salvage Crane Hoist Capacity

For maritime salvage operations, lifting an object through seawater requires calculating net underwater submerged weight:
$$\text{Buoyant Force: } F_B = V \times \rho_{\text{seawater}} \times g \times 10^{-3} \quad (\text{kN})$$
$$\text{Submerged Weight: } W_{\text{submerged}} = \max(0, M_{\text{dry}} \times g - F_B) \quad (\text{kN})$$
$$\text{Submerged Mass: } M_{\text{submerged}} = \frac{W_{\text{submerged}}}{g} \quad (\text{metric tons})$$

### Recommended Dynamic Crane Capacity
Marine salvage operations introduce dynamic swell and suction forces. MarineScan applies a **1.5× dynamic safety factor**:
$$\text{Crane Lift Rating} = M_{\text{submerged}} \times 1.5 \quad (\text{metric tons})$$

---

## 5. Hydrodynamic Seabed Stability Index

Evaluates whether ocean bottom currents will push or slide debris along the seafloor:
1. **Current Drag Force**:
   $$F_D = \frac{1}{2} \rho_{\text{seawater}} C_d A_{\text{frontal}} v_{\text{current}}^2 \times 10^{-3} \quad (\text{kN})$$
2. **Sediment Friction Holding Force**:
   $$F_f = \mu_{\text{sediment}} \times W_{\text{submerged}} \quad (\text{kN})$$

### Sediment Friction Coefficients ($\mu_{\text{sediment}}$)
- `fine_sand`: $\mu = 0.55$
- `coarse_sand`: $\mu = 0.65$
- `mud_silt`: $\mu = 0.40$
- `gravel_pebble`: $\mu = 0.70$
- `rock_reef`: $\mu = 0.85$

### Stability Index ($S$)
$$S_{\text{stability}} = \frac{F_f}{\max(0.001, F_D)}$$

| Stability Index ($S$) | Mobility Classification | Risk Implication |
|---|---|---|
| $S \ge 1.5$ | `Settled / Stable in Sediment` | Debris is anchored by gravity; negligible movement |
| $1.0 \le S < 1.5$ | `Marginal / Scour Risk` | Currents may scour seabed around debris edges |
| $S < 1.0$ | `Unstable / Migrating Debris Hazard` | Debris will slide across seafloor; active collision hazard |

---

## API Endpoints & Usage

- **`GET /api/v1/physics/environment`**: Calculate sound speed, absorption, and wavelength for specified ocean conditions.
- **`POST /api/v1/physics/analyze-target`**: Compute 3D volume, mass, crane hoist rating, and seabed stability for a single target.
- **`POST /api/v1/physics/analyze-image`**: Execute end-to-end detection + shadow + physics synthesis.

### Ocean Environment Calculation Example

#### macOS / Linux (cURL)
```bash
curl -X GET "http://localhost:8000/api/v1/physics/environment?temperature_c=18.5&salinity_psu=35.0&depth_m=45.0&frequency_khz=455.0"
```

#### Windows (PowerShell)
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/physics/environment?temperature_c=18.5&salinity_psu=35.0&depth_m=45.0&frequency_khz=455.0" -Method Get
```
