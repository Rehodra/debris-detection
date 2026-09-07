import React from 'react';
import { ArrowRight, PlayCircle } from 'lucide-react';
import styles from './LandingHero.module.scss';

interface Props {
  onEnterApp?: () => void;
}

export const LandingHero: React.FC<Props> = ({ onEnterApp }) => {
  return (
    <section id="home" className={styles.hero}>
      <div className={styles.overlay} />
      <div className={styles.content}>
        <h1>AQUATRACE</h1>
        <p>
          Autonomous side-scan sonar analysis that detects, classifies, and verifies
          underwater targets in real time — built for scientific-grade survey teams.
        </p>
        <div className={styles.ctaRow}>
          <button className={styles.primaryBtn} onClick={onEnterApp}>
            Start Sonar Analysis <ArrowRight size={16} />
          </button>
          <button className={styles.secondaryBtn}>
            <PlayCircle size={16} /> View Live Demo
          </button>
        </div>
      </div>
    </section>
  );
};

export default LandingHero;