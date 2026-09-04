import React from 'react';
import { Radar, ShieldCheck, Waves, ArrowRight, PlayCircle } from 'lucide-react';
import styles from './Hero.module.scss';

interface HeroProps {
  onLaunchAnalysis?: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onLaunchAnalysis }) => {
  return (
    <section className={styles.heroCard}>
      <div className={styles.heroGlow}></div>

      <div className={styles.heroInner}>
        <div className={styles.heroText}>
          <span className={styles.eyebrow}>
            <Radar size={13} /> AI-POWERED SONAR INTELLIGENCE
          </span>

          <h1 className={styles.heroTitle}>
            See What The <span className={styles.gradientWord}>Ocean Hides.</span>
          </h1>

          <p className={styles.heroSubtitle}>
            AquaTrace analyzes live side-scan sonar feeds in real time — detecting
            ghost nets, submerged pipelines, wreckage, and disaster debris beneath
            the surface before they become hazards.
          </p>

          <div className={styles.heroActions}>
            <button className={styles.primaryBtn} onClick={onLaunchAnalysis}>
              Start Sonar Analysis <ArrowRight size={16} />
            </button>
            <button className={styles.ghostBtn}>
              <PlayCircle size={16} /> View Live Demo
            </button>
          </div>

          <div className={styles.trustRow}>
            <div className={styles.trustItem}>
              <h3>14,204</h3>
              <span>Frames Analyzed</span>
            </div>
            <div className={styles.trustDivider}></div>
            <div className={styles.trustItem}>
              <h3>97.2%</h3>
              <span>Detection Accuracy</span>
            </div>
            <div className={styles.trustDivider}></div>
            <div className={styles.trustItem}>
              <h3>42+</h3>
              <span>Surveys Completed</span>
            </div>
          </div>
        </div>

        <div className={styles.heroVisual}>
          <div className={styles.radarRing1}></div>
          <div className={styles.radarRing2}></div>
          <div className={styles.radarRing3}></div>
          <div className={styles.radarSweep}></div>

          <div className={styles.radarCore}>
            <Waves size={26} />
          </div>

          <div className={`${styles.detectionPing} ${styles.pingRed}`}>
            <span className={styles.pingDot}></span>
            <span className={styles.pingLabel}>GHOST_NET</span>
          </div>

          <div className={`${styles.detectionPing} ${styles.pingAmber}`}>
            <span className={styles.pingDot}></span>
            <span className={styles.pingLabel}>SUB_PIPE</span>
          </div>

          <div className={styles.visualBadge}>
            <ShieldCheck size={13} /> Real-time YOLO Classification
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;