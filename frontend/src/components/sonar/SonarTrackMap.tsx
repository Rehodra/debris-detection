import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, WMSTileLayer, Polyline, CircleMarker, Marker, Popup, useMap } from 'react-leaflet';
import L, { type LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { createTargetPinIcon } from '../../utils/mapPins';
import { MapPin, Navigation, AlertTriangle, Crosshair } from 'lucide-react';
import { MasterTargetResult, SonarNavigationTrack } from '../../api/client';
import styles from './SonarTrackMap.module.scss';

export interface SonarTrackMapProps {
  track: SonarNavigationTrack | null;
  targets: MasterTargetResult[];
  selectedTargetId: string | null;
  onSelectTarget?: (id: string) => void;
  vesselFix?: { latitude: number; longitude: number } | null;
  className?: string;
}

const CLASS_COLORS: Record<string, string> = {
  shipwreck: '#E63946',
  pipe: '#F4A261',
  ghost_net: '#E76F51',
  marine_debris: '#E9C46A',
  aircraft: '#D62828',
  other: '#457B9D',
  fish: '#2A9D8F',
};

function getClassColor(className: string): string {
  return CLASS_COLORS[className.toLowerCase()] ?? '#0284c7';
}

const FitBounds: React.FC<{ bounds: LatLngBoundsExpression | null }> = ({ bounds }) => {
  const map = useMap();
  const appliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!bounds) return;
    const key = JSON.stringify(bounds);
    if (appliedRef.current === key) return;
    appliedRef.current = key;
    try {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 16 });
    } catch {
      // Ignore fit bounds if map view isn't fully ready
    }
  }, [bounds, map]);

  return null;
};

export const SonarTrackMap: React.FC<SonarTrackMapProps> = ({
  track,
  targets,
  selectedTargetId,
  onSelectTarget,
  vesselFix,
  className = '',
}) => {
  // Extract ordered ping track coordinates: [latitude, longitude]
  const trackLatLngs: [number, number][] = [];
  if (track?.points) {
    for (const pt of track.points) {
      if (
        pt.latitude != null &&
        pt.longitude != null &&
        !isNaN(pt.latitude) &&
        !isNaN(pt.longitude) &&
        !(pt.latitude === 0 && pt.longitude === 0)
      ) {
        trackLatLngs.push([pt.latitude, pt.longitude]);
      }
    }
  }

  // Extract georeferenced target coordinates
  const validTargets = targets.filter((t) => {
    const lat = t.coordinates?.latitude ?? t.georeference?.latitude;
    const lon = t.coordinates?.longitude ?? t.georeference?.longitude;
    return (
      lat != null &&
      lon != null &&
      !isNaN(lat) &&
      !isNaN(lon) &&
      !(lat === 0 && lon === 0)
    );
  });

  const allPoints: [number, number][] = [...trackLatLngs];
  for (const t of validTargets) {
    const lat = t.coordinates?.latitude ?? t.georeference?.latitude;
    const lon = t.coordinates?.longitude ?? t.georeference?.longitude;
    if (lat != null && lon != null) {
      allPoints.push([lat, lon]);
    }
  }

  if (vesselFix && vesselFix.latitude !== 0 && vesselFix.longitude !== 0) {
    allPoints.push([vesselFix.latitude, vesselFix.longitude]);
  }

  const hasCoordinates = allPoints.length > 0;
  const bounds: LatLngBoundsExpression | null = hasCoordinates ? allPoints : null;
  const defaultCenter: [number, number] = hasCoordinates ? allPoints[0] : [13.05, 80.42];

  const startPt = trackLatLngs.length > 0 ? trackLatLngs[0] : null;
  const endPt = trackLatLngs.length > 1 ? trackLatLngs[trackLatLngs.length - 1] : null;

  return (
    <div className={`${styles.trackMapContainer} ${className}`}>
      <div className={styles.mapHeader}>
        <div className={styles.headerLeft}>
          <Navigation size={13} className={styles.navIcon} />
          <span>SONAR ACQUISITION TRACK & GEOLOCATIONS</span>
        </div>
        <div className={styles.headerRight}>
          {track && (
            <span className={styles.trackBadge}>
              {track.available_navigation_pings} / {track.total_pings} PINGS LOGGED
            </span>
          )}
          <span className={styles.targetBadge}>{validTargets.length} TARGETS PLOTTED</span>
        </div>
      </div>

      <div className={styles.mapWrap}>
        {!hasCoordinates ? (
          <div className={styles.noCoordsOverlay}>
            <AlertTriangle size={32} className={styles.alertIcon} />
            <h4>Navigation Coordinates Unavailable</h4>
            <p>
              This survey analysis does not contain recorded WGS84 GPS fixes or acoustic track telemetry.
              Coordinates are not fabricated (never defaulting to 0,0).
            </p>
          </div>
        ) : (
          <MapContainer
            center={defaultCenter}
            zoom={13}
            scrollWheelZoom
            style={{ height: '100%', width: '100%', background: '#071526' }}
          >
            {/* OpenStreetMap Base Layer */}
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            {/* INCOIS GEBCO Bathymetry Layer.
                Low opacity is intentional: this WMS returns a solid-fill red/orange/yellow
                depth-ramp raster (not a sparse contour overlay), so anything above ~0.15-0.2
                visually drowns the OSM base map and survey markers underneath it. */}
            <WMSTileLayer
              url="https://incois.gov.in/geoserver/BathymteryImage/wms"
              layers="BathymteryImage:gebcobathymtery"
              format="image/png"
              transparent
              opacity={0.18}
              attribution="Bathymetry: INCOIS"
            />

            {/* Survey Acquisition Track Polyline */}
            {trackLatLngs.length > 1 && (
              <>
                <Polyline
                  positions={trackLatLngs}
                  pathOptions={{
                    color: '#0284c7',
                    weight: 3,
                    opacity: 0.9,
                    dashArray: '6, 6',
                  }}
                />
                {startPt && (
                  <CircleMarker
                    center={startPt}
                    radius={6}
                    pathOptions={{ color: '#22c55e', fillColor: '#22c55e', fillOpacity: 0.9 }}
                  >
                    <Popup>
                      <strong>SURVEY START</strong>
                      <br />
                      Ping 0 · Lat: {startPt[0].toFixed(5)}, Lon: {startPt[1].toFixed(5)}
                    </Popup>
                  </CircleMarker>
                )}
                {endPt && (
                  <CircleMarker
                    center={endPt}
                    radius={6}
                    pathOptions={{ color: '#eab308', fillColor: '#eab308', fillOpacity: 0.9 }}
                  >
                    <Popup>
                      <strong>SURVEY END</strong>
                      <br />
                      Ping {trackLatLngs.length - 1} · Lat: {endPt[0].toFixed(5)}, Lon: {endPt[1].toFixed(5)}
                    </Popup>
                  </CircleMarker>
                )}
              </>
            )}

            {/* Sensor / Vessel Reference Position */}
            {vesselFix && vesselFix.latitude !== 0 && vesselFix.longitude !== 0 && (
              <CircleMarker
                center={[vesselFix.latitude, vesselFix.longitude]}
                radius={7}
                pathOptions={{ color: '#38bdf8', fillColor: '#0284c7', fillOpacity: 0.85, weight: 2 }}
              >
                <Popup>
                  <strong>SURVEY ORIGIN FIX</strong>
                  <br />
                  {vesselFix.latitude.toFixed(5)}°N, {vesselFix.longitude.toFixed(5)}°E
                </Popup>
              </CircleMarker>
            )}

            {/* Geolocated Target Pin Markers */}
            {validTargets.map((target, idx) => {
              const lat = target.coordinates?.latitude ?? target.georeference?.latitude!;
              const lon = target.coordinates?.longitude ?? target.georeference?.longitude!;
              const color = getClassColor(target.class_name);
              const isSelected = selectedTargetId === target.detection_id;
              const pinIcon = createTargetPinIcon(color, isSelected, idx + 1);

              return (
                <Marker
                  key={target.detection_id}
                  position={[lat, lon]}
                  icon={pinIcon}
                  zIndexOffset={isSelected ? 1000 : 100}
                  eventHandlers={{
                    click: () => onSelectTarget?.(target.detection_id),
                  }}
                >
                  <Popup>
                    <div className={styles.popupContent}>
                      <strong>#{idx + 1} {target.display_name.toUpperCase()}</strong>
                      <div className={styles.popupMeta}>
                        <span>Class: {target.class_name}</span>
                        <span>Confidence: {Math.round((target.calibrated_confidence ?? target.ai_confidence ?? 0.9) * 100)}%</span>
                        <span>Risk: {target.risk_tier} ({Math.round(target.risk_score)})</span>
                        <span>Position: {lat.toFixed(5)}°N, {lon.toFixed(5)}°E</span>
                        {target.dimensions?.length_m && (
                          <span>Dimensions: {target.dimensions.length_m.toFixed(1)}m × {target.dimensions.width_m?.toFixed(1) ?? '—'}m</span>
                        )}
                        {target.clearance?.clearance_m != null && (
                          <span>Clearance: {target.clearance.clearance_m.toFixed(1)} m</span>
                        )}
                      </div>
                    </div>
                  </Popup>
                </Marker>
              );
            })}

            <FitBounds bounds={bounds} />
          </MapContainer>
        )}
      </div>
    </div>
  );
};

export default SonarTrackMap;
