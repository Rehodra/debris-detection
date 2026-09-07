import { Mail, MapPinned, Settings2 } from "lucide-react";
import type { Page } from "../App";

interface FooterProps { onNavigate: (page: Page) => void; }

export default function Footer({ onNavigate }: FooterProps) {
  const links: { id: Page; label: string }[] = [
    { id: "home", label: "Overview" },
    { id: "sonar-analysis", label: "Sonar analysis" },
    { id: "map", label: "Detection map" },
    { id: "reports", label: "Mission reports" },
    { id: "how-it-works", label: "How it works" },
  ];

  return <footer className="site-footer" style={{ fontFamily: "var(--font-body)" }}>
    <div className="footer-inner">
      <div className="footer-brand">
        <div className="footer-brand__identity"><img src="/logo.png" alt="AquaTrace" /><div><strong>AquaTrace</strong><span>Mapping the depths to save lives</span></div></div>
        <p>Explainable sonar intelligence for safer navigation, better surveys, and faster marine response.</p>
        <span className="footer-code">AQUATRACE / OPERATIONAL INTELLIGENCE</span>
      </div>
      <div className="footer-columns">
        <div><strong>Explore</strong>{links.map((link) => <button key={link.id} onClick={() => onNavigate(link.id)}>{link.label}</button>)}</div>
        <div><strong>Support</strong><button onClick={() => onNavigate("how-it-works")}><MapPinned size={15} /> Field guide</button><button><Mail size={15} /> Contact us</button><button><Settings2 size={15} /> System settings</button></div>
      </div>
      <div className="footer-bottom"><span>AquaTrace / Mapping the depths to save lives</span><span>Built for the water, not the cloud</span></div>
    </div>
  </footer>;
}
