import React from 'react';
import { ArrowRight, PlayCircle } from 'lucide-react';
import styles from './Hero.module.scss';

interface HeroProps {
  onLaunchAnalysis?: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onLaunchAnalysis }) => {
  return (
    <section className={styles.heroCard}>
      <video
        className={styles.heroVideo}
        src="/hero.mp4"
        autoPlay
        loop
        muted
        playsInline
      />
      <div className={styles.overlay}>
        <div className={styles.heroContent}>
          <h1 className={styles.animatedText}>AquaTrace</h1>
          <div className={styles.heroActions}>
            <button className={styles.primaryBtn} onClick={onLaunchAnalysis}>
              Start Sonar Analysis <ArrowRight size={16} />
            </button>
            <button className={styles.ghostBtn} onClick={onLaunchAnalysis}>
              <PlayCircle size={16} /> View Live Demo
            </button>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;