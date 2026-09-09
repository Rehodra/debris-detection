import React, { useState, useEffect } from 'react';
import type { FeatureCollection, Point } from 'geojson';
import { SurveyMap } from '../components/SurveyMap';
import styles from './History.module.scss';

const API_BASE = 'http://127.0.0.1:8000';

interface AnalysisHistoryItem {
  mission_id: string;
  created_at: string;
  filename: string;
  vessel_lat: number;
  vessel_lon: number;
  total_targets: number;
  verified_targets: number;
  max_risk_tier: string | null;
  class_breakdown: Record<string, number>;
}

interface AnalysisDetail {
  mission_id: string;
  geojson: FeatureCollection<Point>;
  targets: Array<{
    detection_id: string;
    display_name: string;
    calibrated_confidence: number;
    trust_tier: string;
    risk_tier: string;
  }>;
  summary: { primary_alert_message: string };
}

export const History: React.FC = () => {
  const [history, setHistory] = useState<AnalysisHistoryItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnalysisDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/analyses/history?limit=100`)
      .then((r) => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`);
        return r.json();
      })
      .then(setHistory)
      .catch(() => {
        setHistory([]);
        setError('Could not reach the analysis backend.');
      });
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    setDetail(null);
    setDetailError(null);
    fetch(`${API_BASE}/api/v1/analyses/history/${selectedId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`);
        return r.json();
      })
      .then(setDetail)
      .catch(() => setDetailError('Could not load this record.'));
  }, [selectedId]);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1>Analysis History</h1>
        <p>Every analysis actually persisted by the backend — no synthetic or demo entries</p>
      </header>

      <div className={styles.body}>
        <div className={styles.listPanel}>
          {history === null ? (
            <div className={styles.emptyState}>Loading…</div>
          ) : error ? (
            <div className={styles.emptyState}>{error}</div>
          ) : history.length === 0 ? (
            <div className={styles.emptyState}>No analyses recorded yet.</div>
          ) : (
            history.map((h) => (
              <button
                key={h.mission_id}
                className={`${styles.row} ${selectedId === h.mission_id ? styles.rowActive : ''}`}
                onClick={() => setSelectedId(h.mission_id)}
              >
                <div className={styles.rowMain}>
                  <span className={styles.rowFilename}>{h.filename}</span>
                  <span className={styles.rowTime}>{new Date(h.created_at).toLocaleString()}</span>
                </div>
                <div className={styles.rowMeta}>
                  <span>{h.total_targets} target{h.total_targets === 1 ? '' : 's'}</span>
                  <span>{h.verified_targets} verified</span>
                  <span>{h.max_risk_tier ?? 'no risk'}</span>
                </div>
              </button>
            ))
          )}
        </div>

        <div className={styles.detailPanel}>
          {!selectedId ? (
            <div className={styles.emptyState}>Select an analysis to view its detail and map.</div>
          ) : detailError ? (
            <div className={styles.emptyState}>{detailError}</div>
          ) : !detail ? (
            <div className={styles.emptyState}>Loading…</div>
          ) : (
            <>
              <h3>{detail.mission_id}</h3>
              <p className={styles.alertMessage}>{detail.summary.primary_alert_message}</p>
              <SurveyMap geojson={detail.geojson} />
              <table className={styles.miniTable}>
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Trust Tier</th>
                    <th>Risk</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.targets.map((t) => (
                    <tr key={t.detection_id}>
                      <td>{t.display_name}</td>
                      <td>{t.trust_tier}</td>
                      <td>{t.risk_tier}</td>
                      <td>{(t.calibrated_confidence * 100).toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default History;
