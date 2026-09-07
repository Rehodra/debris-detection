import React from 'react';
import { Radio, Github, Mail, MapPin } from 'lucide-react';
import styles from './LandingFooter.module.scss';

export const LandingFooter: React.FC = () => {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerTop}>
        <div className={styles.footerBrand}>
          <div className={styles.brandMark}><Radio size={16} /></div>
          <div>
            <h4>AquaTrace</h4>
            <p>Underwater debris & disaster detection, powered by real-time sonar AI.</p>
          </div>
        </div>

        <div className={styles.footerCol}>
          <h5>Platform</h5>
          <a href="#home">Home</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#accidents">Safety</a>
        </div>

        <div className={styles.footerCol}>
          <h5>Contact</h5>
          <a href="#"><Mail size={13} /> support@aquatrace.io</a>
          <a href="#"><Github size={13} /> github.com/AquaTrace</a>
        </div>
      </div>

      <div className={styles.footerBottom}>
        <span>© 2026 AquaTrace. All rights reserved.</span>
        <div className={styles.footerStatus}>
          <span className={styles.dotGreen}><Radio size={12} /> Sonar Online</span>
          <span className={styles.dotGreen}><MapPin size={12} /> GPS Fixed</span>
        </div>
      </div>
    </footer>
  );
};

export default LandingFooter;