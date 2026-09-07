import React from 'react';
import { Waves, ShieldAlert, SlidersHorizontal } from 'lucide-react';
import styles from './HowItWorks.module.scss';

const FEATURES = [
  {
    icon: Waves,
    title: 'Underwater Sonar Imaging',
    desc: 'AquaTrace processes raw side-scan sonar returns into clean acoustic imagery, filtering seabed noise while preserving true object shadows.',
  },
  {
    icon: ShieldAlert,
    title: 'Disaster Prevention',
    desc: 'By flagging hazards like entangled debris, wreckage, and obstructions early, AquaTrace helps survey crews avoid underwater accidents before they happen.',
  },
  {
    icon: SlidersHorizontal,
    title: 'Editable Detections',
    desc: 'Every detection is reviewable — confirm, reclassify, or dismiss targets yourself, keeping a human in the loop for every hazard call.',
  },
];

export const HowItWorks: React.FC = () => {
  return (
    <section id="how-it-works" className={styles.section}>
      <div className={styles.heading}>
        <span className={styles.eyebrow}>HOW IT WORKS</span>
        <h2>Scientific-grade detection, built for the field</h2>
        <p>
          AquaTrace combines acoustic shadow analysis and trained detection models to
          find and verify underwater targets other systems miss.
        </p>
      </div>

      <div className={styles.grid}>
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div key={title} className={styles.card}>
            <div className={styles.iconWrap}><Icon size={22} /></div>
            <h3>{title}</h3>
            <p>{desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
};

export default HowItWorks;