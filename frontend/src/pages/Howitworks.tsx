import { ArrowRight, Bot, FileCheck2, MapPinned, Waves } from "lucide-react";
import type { Page } from "../App";

interface HowItWorksProps { onNavigate: (page: Page) => void; }

const stages = [
  { number: "01", title: "Geotag & Report", icon: MapPinned, image: "/map.jpg", text: "Each surviving detection is assigned a precise geographic coordinate derived from the vessel GPS track, sonar heading, and along-track distance. Results are written to an in-memory log, visualised on the on-board map, and exported as structured JSON and/or CSV upon mission completion." },
  { number: "02", title: "Prepare the signal", icon: Bot, image: "/2nd.jpg", text: "Morphological filtering removes speckle and normalizes the acoustic field, keeping meaningful silhouettes intact for the model." },
  { number: "03", title: "Validate with physics", icon: FileCheck2, image: "/3rd.jpg", text: "YOLO proposes candidates. Shadow geometry, image quality, and confidence calibration then test whether each candidate is physically plausible." },
  { number: "04", title: "Map what matters", icon: Waves, image: "/4th.jpg", text: "Verified targets receive coordinates, dimensions, risk tiers, and export-ready recommendations for the survey team." },
];

function StageImage({ src, title }: { src: string; title: string }) {
  return <div className="workflow-stage__image"><img src={src} alt={title} onError={(event) => { event.currentTarget.style.display = "none"; }} /><span>AquaTrace / process image</span></div>;
}

export default function HowItWorks({ onNavigate }: HowItWorksProps) {
  return (
    <div className="workflow-page page-enter">
      <section className="workflow-hero"><div className="page-shell"><p className="eyebrow eyebrow--light"><span /> System architecture</p><h1>How AquaTrace<br /><em>sees what is hidden.</em></h1><p>Four evidence-led stages turn an acoustic return into a clear, geospatially useful decision. Built for scientific review, field conditions, and accountable action.</p></div></section>
      <section className="workflow-stages"><div className="page-shell">{stages.map(({ number, title, icon: Icon, image, text }, index) => <article className="workflow-stage" key={number}><div className="workflow-stage__copy"><div className="workflow-stage__number">{number} <span /></div><Icon className="workflow-stage__icon" size={25} /><h2>{title}</h2><p>{index === 0 ? "Each surviving detection is assigned a precise geographic coordinate derived from the vessel GPS track, sonar heading, and along-track distance. Results are written to an in-memory log, visualised on the on-board map, and exported as structured JSON and/or CSV upon mission completion. AquaTrace supports disaster management by helping teams locate hazards, plan response routes, and share reliable evidence with rescue and maritime authorities." : text}</p><div className="workflow-stage__spec"><strong>{index === 0 ? "OPERATIONAL OUTPUT" : index === 1 ? "SIGNAL TREATMENT" : index === 2 ? "EVIDENCE FUSION" : "MAP / REPORT"}</strong><span>{index === 0 ? "MAP / JSON / CSV / RESPONSE" : index === 1 ? "OPENING / CLOSING / NORMALIZE" : index === 2 ? "VISION / SHADOW / QUALITY" : "COORDINATES / RISK / ACTION"}</span></div></div><StageImage src={image} title={title} /></article>)}</div></section>
      <section className="workflow-cta"><div className="page-shell"><p className="eyebrow">Ready for the next mission</p><h2>See the intelligence workspace.</h2><button className="button button--cyan" onClick={() => onNavigate("sonar-analysis")}>Open sonar analysis <ArrowRight size={17} /></button></div></section>
    </div>
  );
}
