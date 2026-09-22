import React, { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, WMSTileLayer, GeoJSON, CircleMarker, Popup, useMap } from 'react-leaflet';
import L, { type Layer, type LatLngBoundsExpression, type LatLng } from 'leaflet';
import type { Feature, FeatureCollection, Point } from 'geojson';
import 'leaflet/dist/leaflet.css';
import { createTargetPinIcon } from '../utils/mapPins';
import styles from './SurveyMap.module.scss';

export interface SensorPosition {
  latitude: number;
  longitude: number;
}

interface SurveyMapProps {
  geojson: FeatureCollection<Point> | null;
  sensorPosition?: SensorPosition | null;
}

const CLASS_COLORS: Record<string, string> = {
  ghost_net: '#dc2626',
  pipe: '#c07d00',
  marine_debris: '#2f6fed',
  shipwreck: '#7c3aed',
  aircraft: '#0891b2',
  mine: '#dc2626',
  unknown: '#6b7490',
};

const colorForClass = (className: string | undefined): string =>
  CLASS_COLORS[(className ?? '').toLowerCase()] ?? '#35c2f0';

const FitBounds: React.FC<{ bounds: LatLngBoundsExpression | null }> = ({ bounds }) => {
  const map = useMap();
  const appliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!bounds) return;
    const key = JSON.stringify(bounds);
    if (appliedRef.current === key) return;
    appliedRef.current = key;
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 16 });
  }, [bounds, map]);

  return null;
};

export const SurveyMap: React.FC<SurveyMapProps> = ({ geojson, sensorPosition }) => {
  const points: [number, number][] = [];
  if (geojson) {
    for (const feature of geojson.features) {
      const [lon, lat] = feature.geometry.coordinates;
      points.push([lat, lon]);
    }
  }
  if (sensorPosition) {
    points.push([sensorPosition.latitude, sensorPosition.longitude]);
  }

  const bounds: LatLngBoundsExpression | null = points.length > 0 ? points : null;
  const center: [number, number] = points.length > 0 ? points[0] : [13.05, 80.28];

  const pointToLayer = (feature: Feature<Point>, latlng: LatLng) => {
    const props = feature.properties ?? {};
    const color = colorForClass(props.class_name);
    return L.marker(latlng, {
      icon: createTargetPinIcon(color, false),
    });
  };

  const onEachFeature = (feature: Feature<Point>, layer: Layer) => {
    const props = feature.properties ?? {};
    const confidencePct = typeof props.confidence === 'number' ? `${(props.confidence * 100).toFixed(1)}%` : 'n/a';
    layer.bindPopup(
      `<strong>${(props.class_name ?? 'unknown').toUpperCase()}</strong><br/>` +
        `Confidence: ${confidencePct}<br/>` +
        (props.dms_string ? `${props.dms_string}<br/>` : '') +
        (typeof props.depth_m === 'number' ? `Depth: ${props.depth_m.toFixed(1)} m` : '')
    );
  };

  return (
    <div className={styles.mapWrap}>
      <MapContainer center={center} zoom={13} scrollWheelZoom style={{ height: '100%', width: '100%' }}>
        {/* Reliable base layer — always renders even if INCOIS is unreachable. */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {/* Real seafloor bathymetry from INCOIS's public GeoServer, layered semi-transparently
            on top. Undocumented government endpoint — if it's ever down or slow, tiles for this
            layer just render blank and the OpenStreetMap base underneath still shows fine. */}
        <WMSTileLayer
          url="https://incois.gov.in/geoserver/BathymteryImage/wms"
          layers="BathymteryImage:gebcobathymtery"
          format="image/png"
          transparent
          opacity={0.55}
          attribution="Bathymetry: INCOIS"
        />
        {geojson && <GeoJSON data={geojson} pointToLayer={pointToLayer} onEachFeature={onEachFeature} />}
        {sensorPosition && (
          <CircleMarker
            center={[sensorPosition.latitude, sensorPosition.longitude]}
            radius={7}
            color="#16a34a"
            weight={3}
            fillColor="#16a34a"
            fillOpacity={0.9}
          >
            <Popup>Vessel / sensor position</Popup>
          </CircleMarker>
        )}
        <FitBounds bounds={bounds} />
      </MapContainer>
    </div>
  );
};

export default SurveyMap;
