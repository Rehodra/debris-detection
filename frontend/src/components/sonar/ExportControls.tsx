import React, { useState } from 'react';
import { Download, FileJson, FileSpreadsheet, Map, Loader2, AlertCircle } from 'lucide-react';
import { downloadExport, ExportFormat } from '../../api/client';
import styles from './ExportControls.module.scss';

export interface ExportControlsProps {
  analysisId: string | null;
  hasTrack?: boolean;
  className?: string;
}

export const ExportControls: React.FC<ExportControlsProps> = ({
  analysisId,
  hasTrack = false,
  className = '',
}) => {
  const [downloadingFormat, setDownloadingFormat] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async (format: ExportFormat) => {
    if (!analysisId) return;
    setError(null);
    setDownloadingFormat(format);
    try {
      await downloadExport(analysisId, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setDownloadingFormat(null);
    }
  };

  if (!analysisId) {
    return (
      <div className={`${styles.exportContainer} ${className}`}>
        <div className={styles.exportHeader}>
          <Download size={13} className={styles.headerIcon} />
          <span>HYDROGRAPHIC EXPORT DATASETS</span>
        </div>
        <div className={styles.disabledNotice}>
          <span>Run or load an analysis to download official hydrographic datasets.</span>
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.exportContainer} ${className}`}>
      <div className={styles.exportHeader}>
        <div className={styles.titleGroup}>
          <Download size={13} className={styles.headerIcon} />
          <span>HYDROGRAPHIC EXPORTS</span>
        </div>
        <span className={styles.missionPill}>{analysisId}</span>
      </div>

      {error && (
        <div className={styles.errorAlert}>
          <AlertCircle size={13} />
          <span>{error}</span>
        </div>
      )}

      <div className={styles.exportGrid}>
        {/* Full Analysis JSON */}
        <button
          type="button"
          className={styles.exportCard}
          onClick={() => handleDownload('json')}
          disabled={downloadingFormat !== null}
          title="Export complete hydrographic intelligence package (JSON)"
        >
          <div className={styles.iconWrap}>
            {downloadingFormat === 'json' ? <Loader2 size={16} className={styles.spinner} /> : <FileJson size={16} />}
          </div>
          <div className={styles.exportText}>
            <strong>Hydrographic JSON</strong>
            <small>Full analysis & telemetry</small>
          </div>
        </button>

        {/* Detections CSV */}
        <button
          type="button"
          className={styles.exportCard}
          onClick={() => handleDownload('csv')}
          disabled={downloadingFormat !== null}
          title="Export target detections and physical dimensions (CSV)"
        >
          <div className={styles.iconWrap}>
            {downloadingFormat === 'csv' ? <Loader2 size={16} className={styles.spinner} /> : <FileSpreadsheet size={16} />}
          </div>
          <div className={styles.exportText}>
            <strong>Detections CSV</strong>
            <small>Targets, bbox, dimensions</small>
          </div>
        </button>

        {/* Targets GeoJSON */}
        <button
          type="button"
          className={styles.exportCard}
          onClick={() => handleDownload('geojson')}
          disabled={downloadingFormat !== null}
          title="Export geolocated targets as RFC 7946 GeoJSON FeatureCollection"
        >
          <div className={styles.iconWrap}>
            {downloadingFormat === 'geojson' ? <Loader2 size={16} className={styles.spinner} /> : <Map size={16} />}
          </div>
          <div className={styles.exportText}>
            <strong>Targets GeoJSON</strong>
            <small>[lon, lat] point features</small>
          </div>
        </button>

        {/* Track GeoJSON */}
        <button
          type="button"
          className={`${styles.exportCard} ${!hasTrack ? styles.cardMuted : ''}`}
          onClick={() => handleDownload('track_geojson')}
          disabled={downloadingFormat !== null || !hasTrack}
          title={hasTrack ? "Export vessel acquisition path as GeoJSON LineString" : "No navigation track available for this scan"}
        >
          <div className={styles.iconWrap}>
            {downloadingFormat === 'track_geojson' ? <Loader2 size={16} className={styles.spinner} /> : <Map size={16} />}
          </div>
          <div className={styles.exportText}>
            <strong>Track GeoJSON</strong>
            <small>Vessel survey path</small>
          </div>
        </button>

        {/* Track CSV */}
        <button
          type="button"
          className={`${styles.exportCard} ${!hasTrack ? styles.cardMuted : ''}`}
          onClick={() => handleDownload('track_csv')}
          disabled={downloadingFormat !== null || !hasTrack}
          title={hasTrack ? "Export ping-by-ping telemetry table in acquisition order (CSV)" : "No navigation track available for this scan"}
        >
          <div className={styles.iconWrap}>
            {downloadingFormat === 'track_csv' ? <Loader2 size={16} className={styles.spinner} /> : <FileSpreadsheet size={16} />}
          </div>
          <div className={styles.exportText}>
            <strong>Track CSV</strong>
            <small>Ping telemetry records</small>
          </div>
        </button>
      </div>
    </div>
  );
};

export default ExportControls;
