import React, { useState } from 'react';
import {
  ShieldAlert,
  Ruler,
  MapPin,
  Anchor,
  AlertTriangle,
  CheckCircle2,
  Info,
  Radio,
  Scale,
  Ship,
  Compass,
} from 'lucide-react';
import { MasterTargetResult } from '../../api/client';
import styles from './TargetInspector.module.scss';

export interface TargetInspectorProps {
  target: MasterTargetResult | null;
  onClose?: () => void;
  className?: string;
}

type TabType = 'overview' | 'dimensions' | 'geodesy' | 'risk';

export const TargetInspector: React.FC<TargetInspectorProps> = ({
  target,
  onClose,
  className = '',
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('overview');

  if (!target) {
    return (
      <div className={`${styles.inspectorEmpty} ${className}`}>
        <Info size={28} className={styles.emptyIcon} />
        <h4>No Target Selected</h4>
        <p>Click on any detected target or selection card to inspect physical dimensions, georeferencing, and maritime risk directives.</p>
      </div>
    );
  }

  const dims = target.dimensions;
  const geo = target.georeference;
  const clearance = target.clearance;
  const shadow = target.shadow_evidence;
  const confPercent = Math.round((target.calibrated_confidence ?? target.ai_confidence ?? 0.9) * 100);

  const getRiskBadgeClass = (riskTier: string) => {
    switch (riskTier?.toUpperCase()) {
      case 'CRITICAL':
        return styles.riskCritical;
      case 'HIGH':
        return styles.riskHigh;
      case 'MODERATE':
        return styles.riskModerate;
      default:
        return styles.riskLow;
    }
  };

  return (
    <div className={`${styles.inspectorContainer} ${className}`}>
      {/* Inspector Header */}
      <div className={styles.inspectorHeader}>
        <div className={styles.headerTitleGroup}>
          <div className={styles.targetTitle}>
            <span className={styles.targetBadge}>TARGET #{target.detection_id}</span>
            <h3>{target.display_name.toUpperCase()}</h3>
          </div>
          <div className={styles.headerBadges}>
            <span className={`${styles.riskBadge} ${getRiskBadgeClass(target.risk_tier)}`}>
              {target.risk_tier} RISK ({Math.round(target.risk_score)})
            </span>
            <span className={styles.trustBadge}>{target.trust_tier.replace(/_/g, ' ')}</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className={styles.tabNav}>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === 'overview' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('overview')}
          >
            <Info size={13} />
            <span>OVERVIEW</span>
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === 'dimensions' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('dimensions')}
          >
            <Ruler size={13} />
            <span>DIMENSIONS</span>
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === 'geodesy' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('geodesy')}
          >
            <MapPin size={13} />
            <span>GEODESY</span>
          </button>
          <button
            type="button"
            className={`${styles.tabBtn} ${activeTab === 'risk' ? styles.tabBtnActive : ''}`}
            onClick={() => setActiveTab('risk')}
          >
            <ShieldAlert size={13} />
            <span>NOTMAR & RISK</span>
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className={styles.tabContent}>
        {/* OVERVIEW TAB */}
        {activeTab === 'overview' && (
          <div className={styles.sectionBody}>
            <div className={styles.metaGrid2}>
              <div className={styles.metaCard}>
                <span className={styles.metaLabel}>CLASS</span>
                <strong>{target.class_name.replace('_', ' ').toUpperCase()}</strong>
              </div>
              <div className={styles.metaCard}>
                <span className={styles.metaLabel}>CONFIDENCE</span>
                <strong className={styles.highlightCyan}>{confPercent}%</strong>
              </div>
              <div className={styles.metaCard}>
                <span className={styles.metaLabel}>AI PROBABILITY</span>
                <strong>{target.ai_confidence ? `${Math.round(target.ai_confidence * 100)}%` : '—'}</strong>
              </div>
              <div className={styles.metaCard}>
                <span className={styles.metaLabel}>CATEGORY</span>
                <strong>{target.category || 'DEBRIS / OBSTRUCTION'}</strong>
              </div>
            </div>

            {/* Acoustic Shadow Corroboration */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Radio size={13} />
                <span>ACOUSTIC SHADOW CORROBORATION</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Shadow Detected:</span>
                  <strong>{shadow?.has_shadow ? 'VERIFIED' : 'NOT DETECTED'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Shadow Score:</span>
                  <strong className={shadow?.has_shadow ? styles.highlightGreen : ''}>
                    {shadow ? `${Math.round(shadow.shadow_score * 100)}%` : '—'}
                  </strong>
                </div>
                {shadow?.shadow_length_m != null && (
                  <div className={styles.propRow}>
                    <span>Shadow Length across Seabed:</span>
                    <strong>{shadow.shadow_length_m.toFixed(2)} m</strong>
                  </div>
                )}
                {shadow?.estimated_height_m != null && (
                  <div className={styles.propRow}>
                    <span>Derived Object Height:</span>
                    <strong className={styles.highlightAmber}>+{shadow.estimated_height_m.toFixed(2)} m</strong>
                  </div>
                )}
                {shadow?.cardinal_direction && (
                  <div className={styles.propRow}>
                    <span>Propagation Direction:</span>
                    <strong>{shadow.cardinal_direction} ({shadow.direction_degrees != null ? `${shadow.direction_degrees.toFixed(0)}°` : ''})</strong>
                  </div>
                )}
              </div>
            </div>

            {/* Quick Location & Dimensions snapshot */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Anchor size={13} />
                <span>TARGET SUMMARY</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Footprint Size:</span>
                  <strong>
                    {dims?.length_m != null ? `${dims.length_m.toFixed(1)}m` : '—'} × {dims?.width_m != null ? `${dims.width_m.toFixed(1)}m` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>WGS84 Coordinates:</span>
                  <strong>
                    {target.coordinates?.latitude != null && target.coordinates?.longitude != null
                      ? `${target.coordinates.latitude.toFixed(5)}°N, ${target.coordinates.longitude.toFixed(5)}°E`
                      : 'Unavailable'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Clearance above Obstruction:</span>
                  <strong className={clearance?.threatens_shallow_draft ? styles.highlightRed : ''}>
                    {clearance?.clearance_m != null ? `${clearance.clearance_m.toFixed(2)} m` : '—'}
                  </strong>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* DIMENSIONS TAB (Phase 10) */}
        {activeTab === 'dimensions' && (
          <div className={styles.sectionBody}>
            <div className={styles.statusBanner}>
              <span className={styles.statusLabel}>MEASUREMENT STATUS:</span>
              <strong className={dims?.measurement_status === 'verified_complete' ? styles.statusGood : styles.statusWarn}>
                {(dims?.measurement_status || 'ESTIMATED').replace(/_/g, ' ').toUpperCase()}
              </strong>
            </div>

            {/* 3D Geometry Extents */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Ruler size={13} />
                <span>REAL-WORLD 3D GEOMETRY</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Along-Track Physical Length:</span>
                  <strong>{dims?.length_m != null ? `${dims.length_m.toFixed(2)} m` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Across-Track Physical Width:</span>
                  <strong>{dims?.width_m != null ? `${dims.width_m.toFixed(2)} m` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Object Height off Seabed:</span>
                  <strong className={styles.highlightAmber}>
                    {dims?.height_m != null ? `+${dims.height_m.toFixed(2)} m` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Seabed Contact Footprint Area:</span>
                  <strong>{dims?.area_sq_m != null ? `${dims.area_sq_m.toFixed(1)} m²` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Volumetric Displacement:</span>
                  <strong>{dims?.estimated_volume_m3 != null ? `${dims.estimated_volume_m3.toFixed(1)} m³` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Pixel Extents (W × H):</span>
                  <span className={styles.dimMuted}>
                    {dims?.pixel_width != null ? `${Math.round(dims.pixel_width)}` : '—'} × {dims?.pixel_height != null ? `${Math.round(dims.pixel_height)}` : '—'} px
                  </span>
                </div>
                {dims?.slant_range_m != null && (
                  <div className={styles.propRow}>
                    <span>Computed Slant Range:</span>
                    <strong>{dims.slant_range_m.toFixed(1)} m</strong>
                  </div>
                )}
                {dims?.ground_range_m != null && (
                  <div className={styles.propRow}>
                    <span>Seabed Ground Range:</span>
                    <strong>{dims.ground_range_m.toFixed(1)} m</strong>
                  </div>
                )}
              </div>
            </div>

            {/* Hydrodynamic & Salvage Engineering */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Scale size={13} />
                <span>SALVAGE & SEABED STABILITY (PHASE 10)</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Estimated Dry Structural Mass:</span>
                  <strong>{dims?.dry_mass_metric_tons != null ? `${dims.dry_mass_metric_tons.toFixed(1)} metric tons` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Underwater Submerged Weight:</span>
                  <strong>{dims?.submerged_weight_kn != null ? `${dims.submerged_weight_kn.toFixed(1)} kN` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Recommended Crane Lift Capacity (1.5× safety):</span>
                  <strong className={styles.highlightCyan}>
                    {dims?.recommended_crane_lift_tons != null ? `${dims.recommended_crane_lift_tons.toFixed(1)} tons` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Seabed Mobility Status:</span>
                  <strong className={dims?.seabed_mobility_status?.includes('Stable') ? styles.highlightGreen : styles.highlightAmber}>
                    {dims?.seabed_mobility_status || 'Settled / Stable'}
                  </strong>
                </div>
                {dims?.seabed_stability_index != null && (
                  <div className={styles.propRow}>
                    <span>Stability Index:</span>
                    <strong>{dims.seabed_stability_index.toFixed(2)}</strong>
                  </div>
                )}
                <div className={styles.propRow}>
                  <span>Measurement Method:</span>
                  <span className={styles.dimMuted}>
                    {(dims?.measurement_method || 'sonar_raster_geometry').replace(/_/g, ' ')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* GEODESY TAB (Detection-to-Geospatial Correlation) */}
        {activeTab === 'geodesy' && (
          <div className={styles.sectionBody}>
            <div className={styles.statusBanner}>
              <span className={styles.statusLabel}>GEOLOCATION STATUS:</span>
              <strong className={geo?.status === 'calculated' ? styles.statusGood : styles.statusWarn}>
                {(geo?.status || (target.coordinates ? 'CALCULATED' : 'UNAVAILABLE')).replace(/_/g, ' ').toUpperCase()}
              </strong>
            </div>

            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Compass size={13} />
                <span>WGS84 COORDINATES</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Latitude:</span>
                  <strong className={styles.highlightCyan}>
                    {target.coordinates?.latitude != null ? `${target.coordinates.latitude.toFixed(6)}°` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Longitude:</span>
                  <strong className={styles.highlightCyan}>
                    {target.coordinates?.longitude != null ? `${target.coordinates.longitude.toFixed(6)}°` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Datum / Coordinate System:</span>
                  <strong>{geo?.coordinate_reference || 'WGS84 (EPSG:4326)'}</strong>
                </div>
                {target.distance_from_sensor_m != null && (
                  <div className={styles.propRow}>
                    <span>Distance from Sensor:</span>
                    <strong>{target.distance_from_sensor_m.toFixed(1)} m</strong>
                  </div>
                )}
                {target.bearing_degrees != null && (
                  <div className={styles.propRow}>
                    <span>True Bearing:</span>
                    <strong>{target.bearing_degrees.toFixed(1)}° True</strong>
                  </div>
                )}
              </div>
            </div>

            {/* Ping Navigation Association */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <MapPin size={13} />
                <span>TELEMETRY ASSOCIATION</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Source Ping Index:</span>
                  <strong>{geo?.source_ping_index != null ? `#${geo.source_ping_index}` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Waterfall Raster Row:</span>
                  <strong>{geo?.waterfall_row != null ? `Scanline ${geo.waterfall_row}` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Across-Track Offset:</span>
                  <strong>
                    {geo?.across_track_offset_m != null
                      ? `${geo.across_track_offset_m > 0 ? '+' : ''}${geo.across_track_offset_m.toFixed(2)} m (${geo.across_track_offset_m >= 0 ? 'Starboard' : 'Port'})`
                      : '—'}
                  </strong>
                </div>
                {geo?.heading_deg != null && (
                  <div className={styles.propRow}>
                    <span>Sensor Heading:</span>
                    <strong>{geo.heading_deg.toFixed(1)}° True</strong>
                  </div>
                )}
                <div className={styles.propRow}>
                  <span>Towfish Layback Applied:</span>
                  <strong>{geo?.layback_applied ? `YES (${geo.layback_distance_m?.toFixed(1) ?? 0}m)` : 'NO'}</strong>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* NOTMAR & RISK TAB (Phase 11) */}
        {activeTab === 'risk' && (
          <div className={styles.sectionBody}>
            {/* NOTMAR Banner */}
            <div className={`${styles.notmarBanner} ${clearance?.threatens_shallow_draft ? styles.notmarUrgent : styles.notmarStandard}`}>
              <ShieldAlert size={20} />
              <div className={styles.notmarBannerText}>
                <h4>
                  {clearance?.threatens_shallow_draft
                    ? 'NOTICE TO MARINERS (NOTMAR) RECOMMENDED'
                    : 'NO IMMEDIATE NOTMAR BROADCAST REQUIRED'}
                </h4>
                <p>
                  {clearance?.threatens_shallow_draft
                    ? 'Target height severely reduces water column clearance (≤ 3.5 m). Presents shallow vessel collision hazard.'
                    : 'Obstruction under-keel clearance exceeds standard shallow-draft hazard thresholds.'}
                </p>
              </div>
            </div>

            {/* Navigational Clearance */}
            <div className={styles.contentBlock}>
              <div className={styles.blockTitle}>
                <Ship size={13} />
                <span>UNDER-KEEL WATER CLEARANCE</span>
              </div>
              <div className={styles.propList}>
                <div className={styles.propRow}>
                  <span>Total Water Depth:</span>
                  <strong>{clearance?.water_depth_m != null ? `${clearance.water_depth_m.toFixed(1)} m` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Target Height:</span>
                  <strong>{clearance?.object_height_m != null ? `${clearance.object_height_m.toFixed(2)} m` : '—'}</strong>
                </div>
                <div className={styles.propRow}>
                  <span>Remaining Water Clearance:</span>
                  <strong className={clearance?.threatens_shallow_draft ? styles.highlightRed : styles.highlightCyan}>
                    {clearance?.clearance_m != null ? `${clearance.clearance_m.toFixed(2)} m` : '—'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Threatens Shallow Draft (≤ 3.5m):</span>
                  <strong className={clearance?.threatens_shallow_draft ? styles.highlightRed : styles.highlightGreen}>
                    {clearance?.threatens_shallow_draft ? 'YES — HAZARD' : 'NO — SAFE'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Threatens Coastal Cargo (≤ 7.5m):</span>
                  <strong className={clearance?.threatens_medium_draft ? styles.highlightAmber : styles.highlightGreen}>
                    {clearance?.threatens_medium_draft ? 'YES — CAUTION' : 'NO — CLEAR'}
                  </strong>
                </div>
                <div className={styles.propRow}>
                  <span>Threatens Deep-Draft Ships (≤ 15m):</span>
                  <strong className={clearance?.threatens_deep_draft ? styles.highlightAmber : styles.highlightGreen}>
                    {clearance?.threatens_deep_draft ? 'YES — CHART WARNING' : 'NO — CLEAR'}
                  </strong>
                </div>
              </div>
            </div>

            {/* Action Recommendations */}
            {target.action_recommendations && target.action_recommendations.length > 0 && (
              <div className={styles.contentBlock}>
                <div className={styles.blockTitle}>
                  <AlertTriangle size={13} />
                  <span>ACTION DIRECTIVES & RECOMMENDATIONS</span>
                </div>
                <div className={styles.recommendationsList}>
                  {target.action_recommendations.map((rec, i) => (
                    <div key={i} className={styles.recommendationItem}>
                      <div className={styles.recHeader}>
                        <span className={styles.recCategory}>{rec.category}</span>
                        <span className={`${styles.recPriority} ${rec.priority === 'IMMEDIATE' ? styles.recImmediate : ''}`}>
                          {rec.priority}
                        </span>
                      </div>
                      <p className={styles.recText}>{rec.action_text}</p>
                      <small className={styles.recStandard}>{rec.authority_standard}</small>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default TargetInspector;
