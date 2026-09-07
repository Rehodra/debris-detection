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
          <p className={styles.heroSubtitle}>
            AI-powered side-scan sonar intelligence for safer oceans. Detect debris, validate acoustic shadows, and turn complex seafloor imagery into precise, actionable maritime insight.

Identify hidden underwater hazards, reduce false alarms, and accurately locate marine debris in real time. Built to support faster decision-making, safer marine operations, and more effective disaster response.

From sonar signals to situational awareness — empowering teams to understand, respond, and protect what lies beneath the surface.
          </p>
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