import React from 'react';
import { Radio } from 'lucide-react';
import styles from './LandingNavbar.module.scss';

interface Props {
  onEnterApp?: () => void;
}

export const LandingNavbar: React.FC<Props> = ({ onEnterApp }) => {
  return (
    <header className={styles.navbar}>
      <div className={styles.brand}>
        <div className={styles.logoMark}><Radio size={17} /></div>
        <span className={styles.brandName}>AquaTrace</span>
      </div>

      <nav className={styles.links}>
        <a href="#home">Home</a>
        <a href="#how-it-works">How It Works</a>
        <a href="#accidents">Safety</a>
      </nav>

      <button className={styles.ctaBtn} onClick={onEnterApp}>
        Launch Dashboard
      </button>
    </header>
  );
};

export default LandingNavbar;