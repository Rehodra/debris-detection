import React from 'react';
import {
  LayoutDashboard, Radio, Eye, Map, History, Activity, Settings
} from 'lucide-react';
import styles from './Sidebar.module.scss';

const NAV_ITEMS = [
  { label: 'Dashboard', icon: LayoutDashboard },
  { label: 'Sonar Analysis', icon: Radio },
  { label: 'Detections', icon: Eye },
  { label: 'Map', icon: Map },
  { label: 'History', icon: History },
  { label: 'System Status', icon: Activity },
];

interface SidebarProps {
  active?: string;
  onNavigate?: (label: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ active = 'Dashboard', onNavigate }) => {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <img src="/logo.png" alt="AquaTrace logo" className={styles.brandLogo} />
        <div className={styles.brandText}>
          <h2>AquaTrace</h2>
          <span>Vessel System</span>
        </div>
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map(({ label, icon: Icon }) => (
          <a
            key={label}
            href="#"
            className={`${styles.navItem} ${active === label ? styles.active : ''}`}
            onClick={(event) => {
              event.preventDefault();
              onNavigate?.(label);
            }}
          >
            <span className={styles.navIcon}><Icon size={17} strokeWidth={2} /></span>
            <span className={styles.navLabel}>{label}</span>
          </a>
        ))}
      </nav>

      <div className={styles.footer}>
        <a href="#" className={styles.navItem} onClick={(event) => event.preventDefault()}>
          <span className={styles.navIcon}><Settings size={17} strokeWidth={2} /></span>
          <span className={styles.navLabel}>Settings</span>
        </a>
      </div>
    </aside>
  );
};

export default Sidebar;
