import React from 'react';
import { ShieldAlert, Anchor, Waves, HelpCircle, ArrowRight } from 'lucide-react';
import styles from './DetectionCard.module.scss';

export type DetectionStatus = 'Verified' | 'Review';

export interface DetectionCardData {
  id: string;
  name: string;
  type: string;
  description: string;
  status: DetectionStatus;
  confidence: number;   // 0-100
  frame: string;
  shadowScore: number;  // 0-100
}

const TYPE_ICONS: Record<string, React.ElementType> = {
  Entanglement: ShieldAlert,
  Infrastructure: Anchor,
  Wreck: Waves,
  Anomaly: HelpCircle,
};

const getScoreTone = (score: number): 'green' | 'amber' | 'red' => {
  if (score >= 75) return 'green';
  if (score >= 45) return 'amber';
  return 'red';
};

export const DetectionCard: React.FC<{ data: DetectionCardData; onView?: (id: string) => void }> = ({ data, onView }) => {
  const Icon = TYPE_ICONS[data.type] ?? HelpCircle;
  const tone = getScoreTone(data.shadowScore);

  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.iconWrap}><Icon size={20} /></div>
        <span className={`${styles.badge} ${styles[data.status === 'Verified' ? 'badgeGreen' : 'badgeAmber']}`}>
          {data.status}
        </span>
        <h3>{data.name}</h3>
        <p className={styles.type}>{data.type}</p>
        <p className={styles.description}>{data.description}</p>
      </div>

      <div className={styles.cardBody}>
        <div className={styles.statsRow}>
          <div className={styles.statCol}>
            <h4>{data.confidence}%</h4>
            <span>CONFIDENCE</span>
          </div>
          <div className={styles.statCol}>
            <h4>{data.frame}</h4>
            <span>FRAME</span>
          </div>
        </div>

        <div className={styles.progressLabelRow}>
          <span>Shadow Score</span>
          <span className={styles[`text-${tone}`]}>{data.shadowScore}%</span>
        </div>
        <div className={styles.progressTrack}>
          <div className={`${styles.progressFill} ${styles[tone]}`} style={{ width: `${data.shadowScore}%` }}></div>
        </div>

        <button className={styles.viewBtn} onClick={() => onView?.(data.id)}>
          View Detection <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
};

export default DetectionCard;