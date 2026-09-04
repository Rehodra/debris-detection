# Component Guide: Geolocation, Towfish Layback & Mapping

The **Geolocation Service** ([`geolocation_service.py`](file:///Users/priyangshu/Desktop/Coding/debris/debris-detection/backend/app/services/geolocation_service.py)) translates 2D sonar waterfall pixel detections $(x, y)$ into precision WGS84 geographic coordinates, Nautical DMS, UTM coordinates, and standard RFC 7946 GeoJSON FeatureCollections for web maps (`MissionMap.jsx`).

---

## The Navigation Coordinate Pipeline

```
  Surface Vessel GNSS (Lat, Lon, Heading)
                    +
          Towfish Cable Payout
                    ↓
       [Towfish Layback Correction]
                    ↓
  Sonar Waterfall Pixel Offset (x, y)
                    ↓
      [Along/Across-Track Vector]
                    ↓
   [Heading Rotation (Navigation Azimuth)]
                    ↓
    [WGS84 Geodetic Projection & UTM]
                    ↓
      GeoJSON / DMS / Mission Map
```

---

## Mathematical Formulations

### 1. Towfish Catenary Layback Calculation
In towed sidescan sonar surveys, the sonar transducer (towfish) is towed behind a surface ship on an armored coaxial or fiber cable. 

To determine the true geographic position of the sensor:
$$\text{Layback} = \sqrt{\max(0, L_{\text{cable}}^2 - D_{\text{depth}}^2)} \times k_{\text{catenary}}$$
where:
- $L_{\text{cable}}$: Cable payout length from vessel stern (m)
- $D_{\text{depth}}$: Towfish operating depth below water surface (m)
- $k_{\text{catenary}}$: Hydrodynamic catenary drag factor (typically $0.92 - 0.98$, default $0.95$)

The towfish position is projected astern of the vessel along the reciprocal heading ($\theta_{\text{vessel}} + 180^\circ$).

---

### 2. Track-Frame Offset Conversion
Using the center nadir ground-track pixel $X_{\text{nadir}}$ and Ground Sampling Distance ($\text{GSD}$):
- **Across-Track Offset** ($\Delta X_{\text{across}}$): Distance perpendicular to heading ($+ \text{Starboard}, - \text{Port}$):
  $$\Delta X_{\text{across}} = (X_{\text{pixel}} - X_{\text{nadir}}) \times \text{GSD}_{\text{across}}$$
- **Along-Track Offset** ($\Delta Y_{\text{along}}$): Distance forward along heading:
  $$\Delta Y_{\text{along}} = (Y_{\text{pixel}} - Y_{\text{ref}}) \times \text{GSD}_{\text{along}}$$

---

### 3. Navigational Azimuth Gyro Heading Rotation
In maritime navigation, $0^\circ = \text{North}$ and $90^\circ = \text{East}$. Converting track-frame offsets into true geographic East and North displacements:
$$\Delta \text{East} = \Delta Y_{\text{along}} \sin\theta + \Delta X_{\text{across}} \cos\theta$$
$$\Delta \text{North} = \Delta Y_{\text{along}} \cos\theta - \Delta X_{\text{across}} \sin\theta$$

- **Sensor Distance**: $D = \sqrt{\Delta \text{East}^2 + \Delta \text{North}^2}$
- **True Bearing**: $\beta = \operatorname{atan2}(\Delta \text{East}, \Delta \text{North}) \pmod{360^\circ}$

---

### 4. WGS84 Geodetic Direct Projection
Projects Cartesian $(\Delta \text{East}, \Delta \text{North})$ displacements onto the WGS84 Reference Ellipsoid ($a = 6378137.0\text{ m}, f = 1/298.257223563, e^2 \approx 0.00669437999014$):
- **Meridional Radius of Curvature**:
  $$R_M = \frac{a(1 - e^2)}{(1 - e^2 \sin^2\phi)^{3/2}}$$
- **Prime Vertical Radius of Curvature**:
  $$R_N = \frac{a}{\sqrt{1 - e^2 \sin^2\phi}}$$
- **Final Geographic Coordinates**:
  $$\text{Latitude: } \phi_{\text{new}} = \phi + \left(\frac{\Delta \text{North}}{R_M}\right) \times \frac{180^\circ}{\pi}$$
  $$\text{Longitude: } \lambda_{\text{new}} = \lambda + \left(\frac{\Delta \text{East}}{R_N \cos\phi}\right) \times \frac{180^\circ}{\pi}$$

---

## Coordinate Formats & GeoJSON Output

Every geolocated target outputs multiple international standards:
1. **Decimal Degrees**: `24.8607000° N, 067.0015947° E`
2. **Nautical DMS**: `24° 51' 38.5" N, 067° 00' 05.7" E`
3. **UTM**: Zone (e.g. `42N`), Easting, and Northing in meters.
4. **RFC 7946 GeoJSON**: Ready for direct ingestion by Leaflet, Mapbox, or `MissionMap.jsx`:
   ```json
   {
     "type": "Feature",
     "geometry": {
       "type": "Point",
       "coordinates": [67.001595, 24.8607]
     },
     "properties": {
       "target_id": "det_5618a0db",
       "class_name": "shipwreck",
       "confidence": 0.78,
       "bearing_deg": 53.9,
       "distance_m": 10.39
     }
   }
   ```

---

## API Endpoints

- **`POST /api/v1/geolocation/layback`**: Calculate towfish coordinates astern of surface vessel from cable payout and depth.
- **`POST /api/v1/geolocation/target`**: Geolocate single pixel target to WGS84, DMS, and UTM.
- **`POST /api/v1/geolocation/analyze-image`**: Execute end-to-end detection + geolocation + GeoJSON export.
