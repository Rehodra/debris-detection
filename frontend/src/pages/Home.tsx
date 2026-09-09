import { ArrowRight } from "lucide-react";
import HowItWorks from "./Howitworks";

import type { Page } from "../App";

interface HomeProps {
  onNavigate: (page: Page) => void;
}

export default function Home({ onNavigate }: HomeProps) {
  return (
    <div className="aquatrace-page">
      <section className="hero-video" aria-labelledby="hero-title">
        <video className="hero-video__media" autoPlay muted loop playsInline>
          <source src="/hero.mp4" type="video/mp4" />
        </video>
        <div className="hero-video__wash" />
        <div className="hero-video__grid" />
        <div className="hero-video__content page-shell">
          <h1 id="hero-title">AQUA<span>TRACE</span></h1>
          <p className="hero-video__tagline">Mapping the depths to save lives.</p>
          <p className="hero-video__summary">Advanced sonar intelligence for detecting underwater debris, validating acoustic evidence, and turning complex seafloor imagery into decisions crews can trust.</p>
          <div className="hero-video__actions">
            <button className="button button--cyan" onClick={() => onNavigate("sonar-analysis")}>Start sonar analysis <ArrowRight size={17} /></button>
            <button className="button button--ghost-light" onClick={() => onNavigate("how-it-works")}>How it works <ArrowRight size={17} /></button>
          </div>
          <div className="hero-video__readout"><span>LIVE SYSTEM PROFILE</span><b /><span>900 kHz</span><b /><span>EDGE-READY</span></div>
        </div>
        <div className="hero-video__scroll">Scroll to explore <span /></div>
      </section>

      <HowItWorks onNavigate={onNavigate} />
    </div>
  );
}
