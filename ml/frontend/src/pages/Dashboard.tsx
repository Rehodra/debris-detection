import React, { useState, useMemo } from 'react';
import {
  Radio, MapPin, Waves, ShieldAlert, TrendingUp,
  Anchor, Activity, ArrowUpRight, Search
} from 'lucide-react';
import { Hero } from '../components/Hero';
import { Footer } from '../components/Footer';
import { DetectionCard, DetectionCardData } from '../components/DetectionCard';
import styles from './Dashboard.module.scss';

interface StatCard {
  label: string;
  value: string;
  delta?: string;
  icon: React.ElementType;
}

const STATS: StatCard[] = [
  { label: 'Total Frames Scanned', value: '14,204', delta: '+312 today', icon: Waves },
  { label: 'Targets Detected', value: '12', delta: '+2 this survey', icon: ShieldAlert },
  { label: 'Verified Targets', value: '4', delta: '33% of total', icon: Anchor },
  { label: 'Survey Coverage', value: '42%', delta: 'S-2023-11A', icon: TrendingUp },
];

const DETECTIONS: DetectionCardData[] = [
  { id: '1', name: 'Ghost Net Entanglement', type: 'Entanglement', description: 'Large drifting net mass flagged near the reef edge, high hazard to marine life.', status: 'Verified', confidence: 91, frame: '0042', shadowScore: 82 },
  { id: '2', name: 'Submerged Pipeline', type: 'Infrastructure', description: 'Linear metallic return consistent with a subsea pipeline segment.', status: 'Review', confidence: 84, frame: '0038', shadowScore: 68 },
  { id: '3', name: 'Unknown Anomaly', type: 'Anomaly', description: 'Irregular acoustic shadow with unclear geometry, requires manual review.', status: 'Review', confidence: 89, frame: '0051', shadowScore: 31 },
  { id: '4', name: 'Shipwreck Debris Field', type: 'Wreck', description: 'Confirmed hull structure with debris scatter consistent with a wreck site.', status: 'Verified', confidence: 96, frame: '0067', shadowScore: 94 },
];

const TYPE_FILTERS = ['All', 'Entanglement', 'Infrastructure', 'Anomaly', 'Wreck'];
const STATUS_FILTERS = ['All', 'Verified', 'Review'];

interface DashboardProps {
  onNavigate?: (page: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ onNavigate }) => {
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('All');
  const [statusFilter, setStatusFilter] = useState('All');

  const filteredDetections = useMemo(() => {
    return DETECTIONS.filter((d) => {
      const matchesSearch = d.name.toLowerCase().includes(search.toLowerCase());
      const matchesType = typeFilter === 'All' || d.type === typeFilter;
      const matchesStatus = statusFilter === 'All' || d.status === statusFilter;
      return matchesSearch && matchesType && matchesStatus;
    });
  }, [search, typeFilter, statusFilter]);

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          <span>VESSEL <strong>RV-Explorer</strong></span>
          <span className={styles.divider}>|</span>
          <span>SURVEY <strong>S-2023-11A</strong></span>
        </div>
        <div className={styles.statusBadges}>
          <span className={styles.badgeSuccess}><Radio size={13} /> SONAR ONLINE</span>
          <span className={styles.badgeSuccess}><MapPin size={13} /> GPS FIX</span>
          <span className={styles.badgeDanger}>EDGE MODE</span>
        </div>
      </header>

      <div className={styles.scrollArea}>
        <Hero onLaunchAnalysis={() => onNavigate?.('Sonar Analysis')} />
        <div className={styles.body}>

          <div className={styles.sectionTitle}>
            <h2>Live Survey Metrics</h2>
            <p>Real-time summary of the current side-scan sonar survey</p>
          </div>

          <div className={styles.statsGrid}>
            {STATS.map(({ label, value, delta, icon: Icon }) => (
              <div className={styles.statCard} key={label}>
                <div className={styles.statIcon}><Icon size={18} /></div>
                <div className={styles.statBody}>
                  <span className={styles.statLabel}>{label}</span>
                  <h2>{value}</h2>
                  {delta && <span className={styles.statDelta}><ArrowUpRight size={12} /> {delta}</span>}
                </div>
              </div>
            ))}
          </div>

          <div className={styles.sectionTitle}>
            <h2>Detected Targets</h2>
            <p>Browse and review objects flagged by the detection pipeline</p>
          </div>

          {/* Search + filter bar */}
          <div className={styles.filterBar}>
            <div className={styles.searchBox}>
              <Search size={16} />
              <input
                type="text"
                placeholder="Search detections by name or type..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className={styles.pillGroup}>
              {TYPE_FILTERS.map((f) => (
                <button
                  key={f}
                  className={`${styles.pill} ${typeFilter === f ? styles.pillActive : ''}`}
                  onClick={() => setTypeFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>

            <div className={styles.pillGroup}>
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f}
                  className={`${styles.pill} ${statusFilter === f ? styles.pillActiveDark : ''}`}
                  onClick={() => setStatusFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Detection cards grid */}
          <div className={styles.detectionsGrid}>
            {filteredDetections.map((d) => (
              <DetectionCard key={d.id} data={d} onView={() => onNavigate?.('Sonar Analysis')} />
            ))}
            {filteredDetections.length === 0 && (
              <div className={styles.emptyState}>No detections match your filters.</div>
            )}
          </div>

          <div className={styles.gridSplit}>
            <div className={styles.panelBlock}>
              <div className={styles.blockHeader}><span>SYSTEM STATUS</span></div>
              <div className={styles.statusList}>
                <div className={styles.statusRow}>
                  <span><Activity size={14} /> Sonar Sensor</span>
                  <span className={styles.dotGreen}>Online</span>
                </div>
                <div className={styles.statusRow}>
                  <span><MapPin size={14} /> GPS Module</span>
                  <span className={styles.dotGreen}>Fixed</span>
                </div>
                <div className={styles.statusRow}>
                  <span><Radio size={14} /> Telemetry Link</span>
                  <span className={styles.dotGreen}>Stable</span>
                </div>
                <div className={styles.statusRow}>
                  <span><ShieldAlert size={14} /> Edge Inference</span>
                  <span className={styles.dotAmber}>Edge Mode</span>
                </div>
              </div>

              <div className={styles.blockTitle}>SURVEY PROGRESS</div>
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: '42%' }}></div>
              </div>
              <div className={styles.progressLabel}>
                <span>42% coverage</span>
                <span>14,204 frames</span>
              </div>
            </div>

            <div className={styles.panelBlockDark}>
              <div className={styles.blockHeaderDark}><span>NEXT SURVEY WINDOW</span></div>
              <p className={styles.darkText}>
                RV-Explorer is scheduled to resume the S-2023-11B transect at 06:00 UTC,
                continuing coverage of the northern reef corridor.
              </p>
              <button className={styles.darkBtn}>View Survey Plan</button>
            </div>
          </div>
        </div>

        <Footer />
      </div>
    </div>
  );
};

export default Dashboard;