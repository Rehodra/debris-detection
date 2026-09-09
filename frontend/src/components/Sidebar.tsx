import { Clock, FileText, Home, Map, ScanLine, Settings2, Workflow } from "lucide-react";
import type { Page } from "../App";

interface SidebarProps {
  currentPage: Page;
  onNavigate: (page: Page) => void;
}

const items: { id: Page; label: string; icon: typeof Home }[] = [
  { id: "home", label: "Mission overview", icon: Home },
  { id: "sonar-analysis", label: "Sonar analysis", icon: ScanLine },
  { id: "map", label: "Detection map", icon: Map },
  { id: "reports", label: "Mission reports", icon: FileText },
  { id: "history", label: "Analysis history", icon: Clock },
  { id: "how-it-works", label: "How AquaTrace works", icon: Workflow },
];

export default function Sidebar({ currentPage, onNavigate }: SidebarProps) {
  return (
    <aside className="workspace-sidebar" aria-label="AquaTrace workspace navigation">
      <div className="workspace-sidebar__status"><span /> SYSTEM ONLINE</div>
      <p className="workspace-sidebar__label">Mission workspace</p>
      <nav className="workspace-sidebar__nav">
        {items.map(({ id, label, icon: Icon }) => (
          <button className={currentPage === id ? "is-active" : ""} key={id} onClick={() => onNavigate(id)}>
            <Icon size={17} strokeWidth={1.8} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      <div className="workspace-sidebar__footer"><Settings2 size={16} /><span>Edge configuration</span><b>READY</b></div>
    </aside>
  );
}
