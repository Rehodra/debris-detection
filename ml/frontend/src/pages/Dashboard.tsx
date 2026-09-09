import React, { useState, useEffect, useMemo } from 'react';
import {
  Waves, ShieldAlert, Anchor, TrendingUp, ArrowUpRight,
  Activity, Database, Cpu,
} from 'lucide-react';
import { Hero } from '../components/Hero';
import { Footer } from '../components/Footer';
import styles from './Dashboard.module.scss';

const API_BASE = 'http://127.0.0.1:8000';

interface AnalysisHistoryItem {
  mission_id: string;
  created_at: string;
  filename: string;
  total_targets: number;
  verified_targets: number;
  max_risk_tier: string | null;
  class_breakdown: Record<string, number>;
}

interface DashboardProps {
  onNavigate?: (page: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const [history, setHistory] = useState<AnalysisHistoryItem[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);
  const [modelInfo, setModelInfo] = useState<{ is_loaded: boolean; total_classes: number } | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/health`)
      .then((r) => setBackendReachable(r.ok))
      .catch(() => setBackendReachable(false));

    fetch(`${API_BASE}/api/v1/models/current`)
      .then((r) => r.json())
      .then((d) => setModelInfo({ is_loaded: d.is_loaded, total_classes: d.total_classes }))
      .catch(() => setModelInfo(null));

    fetch(`${API_BASE}/api/v1/analyses/history?limit=50`)
      .then((r) => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`);
        return r.json();
      })
      .then((d) => setHistory(d))
      .catch(() => {
        setHistory([]);
        setHistoryError('Could not reach the analysis backend.');
      });
  }, []);

  const stats = useMemo(() => {
    const list = history ?? [];
    const totalTargets = list.reduce((sum, h) => sum + h.total_targets, 0);
    const totalVerified = list.reduce((sum, h) => sum + h.verified_targets, 0);
    const latestRiskTier = list[0]?.max_risk_tier ?? 'N/A';
    return {
      analysesRun: list.length,
      totalTargets,
      totalVerified,
      latestRiskTier,
    };
  }, [history]);

  const classBreakdownAllTime = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const h of history ?? []) {
      for (const [cls, count] of Object.entries(h.class_breakdown ?? {})) {
        totals[cls] = (totals[cls] ?? 0) + count;
      }
    }
    return totals;
  }, [history]);

  const STATS = [
    { label: 'Analyses Run', value: String(stats.analysesRun), icon: Waves },
    { label: 'Targets Detected', value: String(stats.totalTargets), icon: ShieldAlert },
    { label: 'Verified Targets', value: String(stats.totalVerified), icon: Anchor },
    { label: 'Latest Risk Tier', value: stats.latestRiskTier, icon: TrendingUp },
  ];

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          <span>MARINESCAN</span>
        </div>
        <div className={styles.statusBadges}>
          {backendReachable === null ? (
            <span className={styles.badgeSuccess}>CHECKING…</span>
          ) : backendReachable ? (
            <span className={styles.badgeSuccess}><Activity size={13} /> BACKEND REACHABLE</span>
          ) : (
            <span className={styles.badgeDanger}>BACKEND UNREACHABLE</span>
          )}
        </div>
      </header>

      <div className={styles.scrollArea}>
        <div className={styles.body}>
          <Hero onLaunchAnalysis={() => onNavigate?.('Sonar Analysis')} />

          <div className={styles.sectionTitle}>
            <h2>Analysis History</h2>
            <p>Real aggregate stats computed from every analysis actually run on this backend</p>
          </div>

          <div className={styles.statsGrid}>
            {STATS.map(({ label, value, icon: Icon }) => (
              <div className={styles.statCard} key={label}>
                <div className={styles.statIcon}><Icon size={18} /></div>
                <div className={styles.statBody}>
                  <span className={styles.statLabel}>{label}</span>
                  <h2>{value}</h2>
                </div>
              </div>
            ))}
          </div>

          <div className={styles.sectionTitle}>
            <h2>Recent Analyses</h2>
            <p>Every image actually run through the detection pipeline, most recent first</p>
          </div>

          <div className={styles.detectionsGrid}>
            {history === null ? (
              <div className={styles.emptyState}>Loading…</div>
            ) : historyError ? (
              <div className={styles.emptyState}>{historyError}</div>
            ) : history.length === 0 ? (
              <div className={styles.emptyState}>
                No analyses yet — <a onClick={() => onNavigate?.('Sonar Analysis')} style={{ cursor: 'pointer', textDecoration: 'underline' }}>upload a sonar image</a> to get started.
              </div>
            ) : (
              history.slice(0, 8).map((h) => (
                <div className={styles.statCard} key={h.mission_id} style={{ alignItems: 'flex-start' }}>
                  <div className={styles.statIcon}><ArrowUpRight size={18} /></div>
                  <div className={styles.statBody}>
                    <span className={styles.statLabel}>{h.filename}</span>
                    <h2 style={{ fontSize: 18 }}>{h.total_targets} target{h.total_targets === 1 ? '' : 's'}</h2>
                    <span className={styles.statDelta}>
                      {new Date(h.created_at).toLocaleString()} · {h.verified_targets} verified · {h.max_risk_tier ?? 'no risk'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className={styles.gridSplit}>
            <div className={styles.panelBlock}>
              <div className={styles.blockHeader}><span>SYSTEM STATUS</span></div>
              <div className={styles.statusList}>
                <div className={styles.statusRow}>
                  <span><Activity size={14} /> Backend API</span>
                  <span className={backendReachable ? styles.dotGreen : styles.dotAmber}>
                    {backendReachable === null ? 'Checking…' : backendReachable ? 'Reachable' : 'Unreachable'}
                  </span>
                </div>
                <div className={styles.statusRow}>
                  <span><Cpu size={14} /> Detection Model</span>
                  <span className={modelInfo?.is_loaded ? styles.dotGreen : styles.dotAmber}>
                    {modelInfo ? `Loaded (${modelInfo.total_classes} classes)` : 'Unknown'}
                  </span>
                </div>
                <div className={styles.statusRow}>
                  <span><Database size={14} /> Analysis History DB</span>
                  <span className={historyError ? styles.dotAmber : styles.dotGreen}>
                    {historyError ? 'Unreachable' : `${history?.length ?? 0} records`}
                  </span>
                </div>
              </div>
            </div>

            <div className={styles.panelBlockDark}>
              <div className={styles.blockHeaderDark}><span>DETECTED CLASSES (ALL TIME)</span></div>
              {Object.keys(classBreakdownAllTime).length === 0 ? (
                <p className={styles.darkText}>No targets detected yet across any analysis.</p>
              ) : (
                <div className={styles.statusList}>
                  {Object.entries(classBreakdownAllTime).map(([cls, count]) => (
                    <div className={styles.statusRow} key={cls}>
                      <span style={{ color: '#eef2ff' }}>{cls}</span>
                      <span style={{ color: '#eef2ff' }}>{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        <Footer />
      </div>
    </div>
  );
};

export default Dashboard;
