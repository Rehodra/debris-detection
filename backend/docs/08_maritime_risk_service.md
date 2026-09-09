# Component Guide: Maritime Risk Assessment & Safety Directives

The **Risk Service** ([`risk_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/risk_service.py)) evaluates multi-dimensional maritime hazards, calculates under-keel draft clearance, assesses fishing trawl snag and subsea pipeline threats, and generates official action advisories (USCG/IMO NOTMAR, IHO S-57).

---

## 1. Under-Keel Navigational Clearance

Detecting subsea debris is only useful if hydrographers know whether ships will strike it. 
MarineScan computes the clear water column depth above the top of the obstruction:
$$\text{Clearance}_{\text{m}} = \text{Water Depth} - H_{\text{object}}$$

### Vessel Draft Vulnerability Tiers
- **Shallow Draft Vulnerability** ($\text{Clearance} \le 3.5\text{m}$): Immediate collision hazard for fishing boats, tugs, and recreational pleasure craft.
- **Medium Draft Vulnerability** ($\text{Clearance} \le 7.5\text{m}$): Hull breach hazard for coastal cargo ships, ferries, and naval vessels.
- **Deep Draft Vulnerability** ($\text{Clearance} \le 15.0\text{m}$): Obstruction to international container carriers, bulk freighters, and VLCC supertankers.

---

## 2. Multi-Factor Hazard Scoring Model

MarineScan calculates a composite risk index in $[0, 100]$ across 5 weighted maritime factors:
$$R_{\text{composite}} = 0.35 \cdot R_{\text{nav}} + 0.20 \cdot R_{\text{trawl}} + 0.20 \cdot R_{\text{infra}} + 0.15 \cdot R_{\text{env}} + 0.10 \cdot R_{\text{mobility}}$$

### Factor Breakdown & 7-Class Hazard Specifics
1. **Navigational Risk ($R_{\text{nav}}$)**: Scaled non-linearly by under-keel clearance ($100.0$ if clearance $\le 3.5\text{m}$).
2. **Trawl Snag Risk ($R_{\text{trawl}}$)**:
   - **`ghost_net`**: Extreme entanglement hazard for commercial bottom trawlers, drift nets, diving operations, and ship propulsion screws.
   - **`pipe`**: Heavy snag hazard where otter boards or dredge gear hook under exposed pipelines, risking cable rupture or vessel capsize.
   - **`shipwreck` / `aircraft`**: High risk of tearing nets on jagged metal superstructures, masts, and airframe wings.
3. **Subsea Infrastructure Threat ($R_{\text{infra}}$)**: Risk to proximate gas/oil pipelines, subsea fiber optic cables, or offshore wind farm lines, factoring in debris mobility under bottom currents.
4. **Environmental Contamination ($R_{\text{env}}$)**: Chemical, toxic paint, heavy metals, and trapped bunker fuel leakage risk (scaled by 3D volumetric displacement).
5. **Seabed Mobility Risk ($R_{\text{mobility}}$)**: Current drift hazard derived from `physics_service.hydrodynamic_stability`.

---

## 3. Categorical Risk Tiers & UI Colors

| Risk Tier | Score Range | Badge Color | Description & Operational Severity |
|---|---|---|---|
| `CRITICAL` | $80 - 100$ | `#E63946` (Red) | Emergency hazard; shallow collision risk ($\le 3.5\text{m}$) or active pipeline collision. Immediate NOTMAR required. |
| `HIGH` | $60 - 79$ | `#F4A261` (Orange) | Significant hazard; medium draft obstruction or severe trawl net snag hazard. |
| `MODERATE` | $40 - 59$ | `#E9C46A` (Amber) | Navigational obstruction to deep-draft ships; charted warning symbol required. |
| `LOW` | $0 - 39$ | `#2A9D8F` (Teal) | Deep water, settled, negligible threat to navigation or infrastructure. |

---

## 4. Standardized Action Recommendations

Generates official directives compliant with international maritime authorities (IHO, USCG, IMO):

- **`[IMMEDIATE] NAVIGATION`**:
  *"Broadcast urgent Notice to Mariners (NOTMAR) warning of shallow obstruction hazard."*
- **`[HIGH] CHARTING`**:
  *"Issue urgent S-57 Electronic Navigational Chart (ENC) update: chart obstruction with least depth X.Xm."*
- **`[HIGH] NAVIGATION`**:
  *"Alert commercial fishing fleets of high snag/entanglement hazard for bottom trawl and drift nets."*
- **`[HIGH] SALVAGE`**:
  *"Establish a 250m subsea work and anchoring exclusion zone around proximate pipeline corridor."*
- **`[STANDARD] ENVIRONMENTAL`**:
  *"Deploy ROV inspection team for environmental survey to assess fuel containment and structural integrity."*

---

## API Endpoints & Cross-Platform Invocations

- **`POST /api/v1/risk/evaluate-target`**: Evaluate multi-factor maritime risk and action recommendations for an individual target.
- **`POST /api/v1/risk/analyze-image`**: Execute end-to-end detection + shadow + physics + confidence + risk assessment.

### Example: Image Risk Analysis

#### macOS / Linux (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/risk/analyze-image" \
  -F "file=@sample_sidescan.png" \
  -F "water_depth_m=35.0" \
  -F "meters_per_pixel=0.05"
```

#### Windows (PowerShell)
```powershell
$form = @{
    file = Get-Item "sample_sidescan.png"
    water_depth_m = "35.0"
    meters_per_pixel = "0.05"
}
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/risk/analyze-image" -Method Post -Form $form
```
