import React, { useState } from 'react';
import { Menu, X, LayoutDashboard, Radio, Eye, Map, History, Activity } from 'lucide-react';
import styles from './Navbar.module.scss';

const NAV_ITEMS = [
  { label: 'Dashboard', icon: LayoutDashboard },
  { label: 'Sonar Analysis', icon: Radio },
  { label: 'Detections', icon: Eye },
  { label: 'Map', icon: Map },
  { label: 'History', icon: History },
  { label: 'System Status', icon: Activity },
];

interface NavbarProps {
  active?: string;
  onNavigate?: (label: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({ active = 'Dashboard', onNavigate }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <nav className={styles.navbar}>
      <div className={styles.navBrand}>
        <img src="/logo.png" alt="AquaTrace" className={styles.logo} />
        <span className={styles.brandText}>AquaTrace</span>
      </div>

      <div className={styles.navLinksDesktop}>
        {NAV_ITEMS.map(({ label }) => (
          <button
            key={label}
            className={`${styles.navLink} ${active === label ? styles.active : ''}`}
            onClick={() => onNavigate?.(label)}
          >
            {label}
          </button>
        ))}
      </div>

      <button className={styles.mobileToggle} onClick={() => setIsOpen(!isOpen)}>
        {isOpen ? <X size={24} /> : <Menu size={24} />}
      </button>

      {isOpen && (
        <div className={styles.navLinksMobile}>
          {NAV_ITEMS.map(({ label, icon: Icon }) => (
            <button
              key={label}
              className={`${styles.navLinkMobile} ${active === label ? styles.active : ''}`}
              onClick={() => {
                onNavigate?.(label);
                setIsOpen(false);
              }}
            >
              <Icon size={18} /> {label}
            </button>
          ))}
        </div>
      )}
    </nav>
  );
};

export default Navbar;
