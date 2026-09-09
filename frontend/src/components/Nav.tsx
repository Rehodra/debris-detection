import { FileText, Home, Map, Menu, ScanLine, Workflow } from "lucide-react";
import type { Page } from "../App";

interface NavProps { currentPage: Page; onNavigate: (page: Page) => void; }

const links: { id: Page; label: string; icon: typeof Home }[] = [
  { id: "home", label: "Overview", icon: Home },
  { id: "sonar-analysis", label: "Sonar analysis", icon: ScanLine },
  { id: "map", label: "Detection map", icon: Map },
  { id: "reports", label: "Reports", icon: FileText },
  { id: "how-it-works", label: "How it works", icon: Workflow },
];

function SonarMark() {
  return <img className="brand-mark" src="/logo.png" alt="" onError={(event) => { event.currentTarget.src = "/aquatrace-mark.svg"; }} />;
}

export default function Nav({ currentPage, onNavigate }: NavProps) {
  return (
    <header className={`site-nav ${currentPage === "home" ? "site-nav--landing" : "site-nav--workspace"}`}>
      <button className="brand-lockup" onClick={() => onNavigate("home")} aria-label="AquaTrace overview">
        <SonarMark /><span><strong>AquaTrace</strong><small>Mapping the depths to save lives</small></span>
      </button>
      <nav className="site-nav__links" aria-label="Primary navigation">
        {links.map(({ id, label, icon: Icon }) => <button className={currentPage === id ? "is-active" : ""} key={id} onClick={() => onNavigate(id)}><Icon size={15} strokeWidth={2} /><span>{label}</span></button>)}
      </nav>
      <div className="site-nav__right"><span className="nav-status"><i /> EDGE MODE / READY</span><button className="nav-upload" onClick={() => onNavigate("sonar-analysis")}><ScanLine size={15} /> Analyze sonar</button><button className="nav-menu" aria-label="Open navigation"><Menu size={20} /></button></div>
    </header>
  );
}
