import React from 'react';
import { Waves, Radio, MapPin, Github, Mail } from 'lucide-react';
import styles from './Footer.module.scss';

export const Footer: React.FC = () => {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerTop}>
        <div className={styles.footerBrand}>
          <div className={styles.brandMark}><Waves size={16} /></div>
          <div>
            <h4>AquaTrace</h4>
            <p>Underwater debris & disaster detection, powered by real-time sonar AI.</p>
          </div>
        </div>

        <div className={styles.footerCol}>
          <h5>Platform</h5>
          <a href="#">Dashboard</a>
          <a href="#">Sonar Analysis</a>
          <a href="#">Detections</a>
          <a href="#">Survey Map</a>
        </div>

        <div className={styles.footerCol}>
          <h5>Resources</h5>
          <a href="#">Documentation</a>
          <a href="#">API Reference</a>
          <a href="#">Detection Models</a>
          <a href="#">Changelog</a>
        </div>

        <div className={styles.footerCol}>
          <h5>Contact</h5>
          <a href="#"><Mail size={13} /> support@AquaTrace.io</a>
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

export default Footer;