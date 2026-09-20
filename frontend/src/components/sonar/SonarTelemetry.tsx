import React from 'react';
import { Activity, Compass, Navigation, Waves, Gauge, Disc } from 'lucide-react';
import { SonarNavigation, SonarRasterMetadata, AnalysisSourceInfo } from '../../api/client';
import styles from './SonarTelemetry.module.scss';

export interface SonarTelemetryProps {
  navigation?: SonarNavigation | null;
  sonarMeta?: SonarRasterMetadata | null;
  source?: AnalysisSourceInfo | null;
  className?: string;
}

export const SonarTelemetry: React.FC<SonarTelemetryProps> = ({
  navigation,
  sonarMeta,
  source,
  className = '',
}) => {
  const formatVal = (val: number | string | null | undefined, unit: string = '', decimals: number = 2) => {
    if (val === null || val === undefined || isNaN(Number(val))) return '—';
    if (typeof val === 'number') {
      return `${val.toFixed(decimals)}${unit ? ` ${unit}` : ''}`;
    }
    return `${val}${unit ? ` ${unit}` : ''}`;
  };

  return (
    <div className={`${styles.telemetryPanel} ${className}`}>
      <div className={styles.telemetryHeader}>
        <div className={styles.headerTitle}>
          <Activity size={13} className={styles.pulseIcon} />
          <span>SONAR TELEMETRY & NAVIGATION FIX</span>
        </div>
        {source?.format && (
          <span className={styles.formatBadge}>{source.format.toUpperCase()}</span>
        )}
      </div>

      <div className={styles.telemetryGrid}>
        {/* Vessel / Sensor Latitude */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Navigation size={12} />
            <span>LATITUDE</span>
          </div>
          <strong>
            {navigation?.latitude != null ? `${navigation.latitude.toFixed(5)}°N` : '—'}
          </strong>
        </div>

        {/* Vessel / Sensor Longitude */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Navigation size={12} />
            <span>LONGITUDE</span>
          </div>
          <strong>
            {navigation?.longitude != null ? `${navigation.longitude.toFixed(5)}°E` : '—'}
          </strong>
        </div>

        {/* Gyro Heading */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Compass size={12} />
            <span>HEADING</span>
          </div>
          <strong>
            {formatVal(navigation?.heading_deg ?? navigation?.heading, '°T', 1)}
          </strong>
        </div>

        {/* Towfish Altitude */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Waves size={12} />
            <span>ALTITUDE</span>
          </div>
          <strong>
            {formatVal(navigation?.altitude_m ?? navigation?.altitude, 'm', 1)}
          </strong>
        </div>

        {/* Sensor Depth */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Gauge size={12} />
            <span>SENSOR DEPTH</span>
          </div>
          <strong>
            {formatVal(navigation?.depth_m ?? navigation?.depth, 'm', 1)}
          </strong>
        </div>

        {/* Slant Range */}
        <div className={styles.telemetryCard}>
          <div className={styles.cardTop}>
            <Disc size={12} />
            <span>SLANT RANGE</span>
          </div>
          <strong>
            {formatVal(sonarMeta?.slant_range_m, 'm', 1)}
          </strong>
        </div>
      </div>

      {/* Auxiliary Metadata Row */}
      <div className={styles.telemetryFooter}>
        <span>Channels: <strong>{sonarMeta?.channel_layout || 'Standard'}</strong></span>
        <span>Pings: <strong>{sonarMeta?.total_pings ?? '—'}</strong></span>
        <span>Resolution: <strong>{formatVal(sonarMeta?.meters_per_pixel, 'm/px', 4)}</strong></span>
        <span>Origin: <strong>{navigation?.source || 'acoustic_telemetry'}</strong></span>
      </div>
    </div>
  );
};

export default SonarTelemetry;
