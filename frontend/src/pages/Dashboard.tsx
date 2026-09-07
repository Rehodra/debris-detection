import { useState, useRef, useEffect, useCallback } from "react";

/* ── Types & constants ────────────────────────────────────── */
type Page = "home" | "dashboard" | "map" | "reports" | "how-it-works";
type Tab = 0 | 1 | 2;

const DETECTIONS = [
  { id: "DET-001", cls: "Entangled Net", conf: 91, lat: "10.4823°N", lon: "72.6341°E", depth: "28 m", color: "#E8604C" },
  { id: "DET-002", cls: "Steel Pipe",    conf: 76, lat: "10.4819°N", lon: "72.6338°E", depth: "29 m", color: "#F2A94E" },
  { id: "DET-003", cls: "Cylinder",      conf: 61, lat: "10.4815°N", lon: "72.6330°E", depth: "31 m", color: "#7C9490" },
  { id: "DET-004", cls: "Entangled Net", conf: 84, lat: "10.4810°N", lon: "72.6325°E", depth: "27 m", color: "#F2A94E" },
  { id: "DET-005", cls: "Shipwreck",     conf: 95, lat: "10.4806°N", lon: "72.6318°E", depth: "34 m", color: "#E8604C" },
];

function ConfPill({ v }: { v: number }) {
  const bg   = v >= 90 ? "#E8604C" : v >= 70 ? "#F2A94E" : "transparent";
  const text = v >= 70 ? "white"   : "#7C9490";
  const bdr  = v < 70  ? "1px solid #7C9490" : "none";
  return (
    <span style={{ background: bg, color: text, border: bdr, borderRadius: "4px",
      fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 600,
      padding: "2px 6px", lineHeight: 1 }}>{v}%</span>
  );
}

/* ── Sonar tile canvas (shared base for all 3 tabs) ───────── */
function useSonarTile(
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  variant: "raw" | "clean" | "shadow" | "yolo"
) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const W = canvas.width, H = canvas.height;

    /* Seeded noise */
    let s = 7919;
    const rng = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 0xffffffff; };

    const id = ctx.createImageData(W, H);
    const px = id.data;

    const OBJ_X = Math.round(W * 0.31), OBJ_Y = Math.round(H * 0.37);
    const OBJ_W = 72, OBJ_H = 36;
    const NADIR = Math.round(W * 0.5);
    const SHADOW_X = OBJ_X + OBJ_W, SHADOW_W = 88;

    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const n = rng();
        const d = Math.abs(x - NADIR) / (W * 0.5);
        let bright = 195 * Math.exp(-d * 3.2) + 55 * (1 - d);
        bright += Math.sin(y * 0.17 + x * 0.05) * 11 + Math.sin(y * 0.06 - x * 0.1) * 7;
        bright += (n - 0.5) * (variant === "raw" ? 60 : 32);

        /* Rock cluster */
        const dRk = Math.hypot(x - Math.round(W * 0.72), (y - Math.round(H * 0.62)) * 1.5);
        if (dRk < 22) bright += (1 - dRk / 22) * 50;
        if (x > Math.round(W*0.72)+16 && x < Math.round(W*0.72)+44 && Math.abs(y-Math.round(H*0.62)) < 12) {
          bright *= 0.28;
        }

        /* Object */
        const inObj = x >= OBJ_X && x < OBJ_X+OBJ_W && y >= OBJ_Y && y < OBJ_Y+OBJ_H;
        if (inObj) {
          const netV = (x-OBJ_X)%10 < 2;
          const netH = (y-OBJ_Y)%8  < 2;
          bright = (netV || netH) ? 215 + n*18 : 158 + n*22;
        }

        /* Shadow */
        const inShadow = x >= SHADOW_X && x < SHADOW_X+SHADOW_W
                      && y >= OBJ_Y-5 && y < OBJ_Y+OBJ_H+5;
        if (inShadow) {
          const fade = (x - SHADOW_X) / SHADOW_W;
          bright = bright * 0.15 * (1-fade*0.7);
        }

        /* Extra speckle for raw */
        if (variant === "raw" && rng() > 0.9) bright += 45 * rng();

        bright = Math.max(0, Math.min(255, bright));

        /* Shadow overlay for tab 2 */
        let r = bright, g = bright * 0.96, b = bright * 0.88;
        if (variant === "shadow" && inShadow) {
          const fade = (x - SHADOW_X) / SHADOW_W;
          const overlay = (1 - fade) * 0.55;
          r = r * (1-overlay) + 46 * overlay;
          g = g * (1-overlay) + 111 * overlay;
          b = b * (1-overlay) + 219 * overlay;
        }

        const i = (y * W + x) * 4;
        px[i] = r; px[i+1] = g; px[i+2] = b; px[i+3] = 255;
      }
    }
    ctx.putImageData(id, 0, 0);

    /* YOLO bounding boxes drawn on top of canvas pixels */
    if (variant === "yolo") {
      /* Detection 1 — high confidence, coral */
      ctx.strokeStyle = "#E8604C";
      ctx.lineWidth = 2;
      ctx.strokeRect(OBJ_X, OBJ_Y, OBJ_W, OBJ_H);
      ctx.fillStyle = "#E8604C";
      ctx.fillRect(OBJ_X, OBJ_Y - 20, 128, 18);
      ctx.fillStyle = "white";
      ctx.font = `bold 10px "IBM Plex Mono", monospace`;
      ctx.fillText("Entangled Net · 91%", OBJ_X + 5, OBJ_Y - 6);
      /* Corner ticks */
      [OBJ_X, OBJ_X+OBJ_W-10].forEach(cx => {
        [OBJ_Y, OBJ_Y+OBJ_H-10].forEach(cy => {
          ctx.strokeStyle = "#E8604C";
          ctx.strokeRect(cx, cy, 10, 10);
        });
      });

      /* Detection 2 — medium confidence, amber */
      const RK_X = Math.round(W*0.64), RK_Y = Math.round(H*0.52);
      ctx.strokeStyle = "#F2A94E";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(RK_X-20, RK_Y-14, 56, 28);
      ctx.fillStyle = "#F2A94E";
      ctx.fillRect(RK_X-20, RK_Y-32, 82, 16);
      ctx.fillStyle = "#132A2E";
      ctx.font = `600 9px "IBM Plex Mono", monospace`;
      ctx.fillText("Steel Pipe · 76%", RK_X-16, RK_Y-20);
    }
  }, [canvasRef, variant]);
}

/* ── Tab 1: Morphological preprocessing ─────────────────── */
function MorphoTab() {
  const rawRef   = useRef<HTMLCanvasElement>(null);
  const cleanRef = useRef<HTMLCanvasElement>(null);
  const [slider, setSlider] = useState(52);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useSonarTile(rawRef,   "raw");
  useSonarTile(cleanRef, "clean");

  const onMove = useCallback((clientX: number) => {
    if (!dragging.current || !containerRef.current) return;
    const r = containerRef.current.getBoundingClientRect();
    setSlider(Math.max(4, Math.min(96, ((clientX - r.left) / r.width) * 100)));
  }, []);

  useEffect(() => {
    const mm = (e: MouseEvent) => onMove(e.clientX);
    const tm = (e: TouchEvent) => onMove(e.touches[0].clientX);
    const up  = () => { dragging.current = false; };
    window.addEventListener("mousemove", mm);
    window.addEventListener("touchmove", tm);
    window.addEventListener("mouseup",   up);
    window.addEventListener("touchend",  up);
    return () => {
      window.removeEventListener("mousemove", mm);
      window.removeEventListener("touchmove", tm);
      window.removeEventListener("mouseup",   up);
      window.removeEventListener("touchend",  up);
    };
  }, [onMove]);

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Before/after slider */}
      <div
        ref={containerRef}
        className="relative overflow-hidden select-none cursor-ew-resize flex-shrink-0"
        style={{ borderRadius: "14px", height: "260px" }}
        onMouseDown={() => { dragging.current = true; }}
        onTouchStart={() => { dragging.current = true; }}
      >
        {/* Clean (after) — full width behind */}
        <canvas ref={cleanRef} width={560} height={260}
          className="absolute inset-0 w-full h-full" style={{ imageRendering: "auto" }}/>

        {/* Raw (before) — clipped on the left */}
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100-slider}% 0 0)` }}>
          <canvas ref={rawRef} width={560} height={260}
            className="w-full h-full" style={{ imageRendering: "auto" }}/>
          {/* "RAW" watermark */}
          <div className="absolute top-3 left-3 text-[10px] text-white/50" style={{fontFamily:"var(--font-mono)"}}>RAW SONAR</div>
        </div>

        {/* "PROCESSED" watermark on right side */}
        <div className="absolute top-3" style={{left:`${Math.min(slider+2, 90)}%`}}>
          <span className="text-[10px] text-[#1C7C72]/70" style={{fontFamily:"var(--font-mono)"}}>PROCESSED</span>
        </div>

        {/* Slider divider */}
        <div className="absolute top-0 bottom-0 w-px bg-white/60" style={{left:`${slider}%`}}>
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 bg-white rounded-full border border-[#1C7C72]/30 flex items-center justify-center"
            style={{ boxShadow: "0 2px 8px rgba(0,0,0,0.25)" }}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M2 7L5 4M2 7L5 10M12 7L9 4M12 7L9 10" stroke="#1C7C72" strokeWidth="1.4" strokeLinecap="round"/>
            </svg>
          </div>
        </div>

        <div className="absolute bottom-3 right-3 text-[9px] text-white/40" style={{fontFamily:"var(--font-mono)"}}>
          drag to compare
        </div>
      </div>

      {/* Logic strip */}
      <div className="bg-[#E4F1EE] p-4 flex-shrink-0" style={{ borderRadius: "4px" }}>
        <div className="text-xs font-semibold text-[#0E4749] mb-1.5" style={{ fontFamily: "var(--font-display)" }}>
          Why this step matters
        </div>
        <p className="text-[11px] text-[#132A2E] leading-relaxed">
          Raw sonar is noisy — every ping has speckle. Morphological opening removes small noise specks; closing fills small gaps inside real objects, so an object's outline survives while random noise doesn't. This is what makes the shapes underneath detectable at all.
        </p>
      </div>
    </div>
  );
}

/* ── Tab 2: Acoustic shadow analysis ────────────────────── */
function ShadowTab() {
  const ref = useRef<HTMLCanvasElement>(null);
  useSonarTile(ref, "shadow");

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="relative flex-shrink-0" style={{ borderRadius: "14px", overflow: "hidden", height: "260px" }}>
        <canvas ref={ref} width={560} height={260}
          className="w-full h-full" style={{ imageRendering: "auto" }}/>

        {/* SVG annotation overlay */}
        <svg
          viewBox="0 0 560 260"
          className="absolute inset-0 w-full h-full pointer-events-none"
          fill="none"
        >
          {/* Object box hint */}
          <rect x="173" y="96" width="72" height="36" rx="1" stroke="#F3FAF8" strokeWidth="0.8" strokeOpacity="0.3"/>

          {/* Shadow length measurement — shadow-blue ONLY */}
          <line x1="247" y1="117" x2="335" y2="117" stroke="#2E6FDB" strokeWidth="2"/>
          <line x1="247" y1="110" x2="247" y2="124" stroke="#2E6FDB" strokeWidth="1.5"/>
          <line x1="335" y1="110" x2="335" y2="124" stroke="#2E6FDB" strokeWidth="1.5"/>

          {/* Label pill */}
          <rect x="255" y="98" width="72" height="14" rx="2" fill="#2E6FDB"/>
          <text x="291" y="108" textAnchor="middle" fill="white" fontSize="7.5" fontFamily="IBM Plex Mono, monospace" fontWeight="600">
            shadow: 1.42 m
          </text>

          {/* Height dashed */}
          <line x1="164" y1="96" x2="164" y2="132" stroke="#F2A94E" strokeWidth="1.5" strokeDasharray="3,2"/>
          <line x1="158" y1="96" x2="170" y2="96" stroke="#F2A94E" strokeWidth="1.5"/>
          <line x1="158" y1="132" x2="170" y2="132" stroke="#F2A94E" strokeWidth="1.5"/>
          <rect x="120" y="106" width="42" height="13" rx="2" fill="#F2A94E"/>
          <text x="141" y="115" textAnchor="middle" fill="#132A2E" fontSize="7.5" fontFamily="IBM Plex Mono, monospace" fontWeight="600">
            h: 0.38 m
          </text>

          {/* Grazing angle arc */}
          <path d="M335 117 A 40 40 0 0 0 368 87" stroke="#7C9490" strokeWidth="1" strokeDasharray="3,2" opacity="0.7"/>
          <text x="370" y="97" fill="#7C9490" fontSize="8" fontFamily="IBM Plex Mono, monospace">θ=15°</text>

          {/* Nadir hint */}
          <line x1="280" y1="0" x2="280" y2="260" stroke="white" strokeWidth="0.5" strokeOpacity="0.12"/>
        </svg>
      </div>

      {/* Measurements row */}
      <div className="flex gap-3">
        {[
          { lbl: "Shadow length", val: "1.42 m", color: "#2E6FDB" },
          { lbl: "Est. height",   val: "0.38 m", color: "#F2A94E" },
          { lbl: "Grazing angle", val: "15.0°",  color: "#7C9490" },
        ].map(m => (
          <div key={m.lbl} className="flex-1 bg-[#F3FAF8] border border-[#E4F1EE] px-3 py-2" style={{borderRadius:"4px"}}>
            <div className="text-[10px] text-[#7C9490] mb-0.5">{m.lbl}</div>
            <div className="text-sm font-semibold" style={{ fontFamily: "var(--font-mono)", color: m.color }}>{m.val}</div>
          </div>
        ))}
      </div>

      {/* Logic strip */}
      <div className="bg-[#EBF1FA] p-4" style={{ borderRadius: "4px" }}>
        <div className="text-xs font-semibold text-[#0E4749] mb-1.5" style={{ fontFamily: "var(--font-display)" }}>
          Shadow-based height estimation
        </div>
        <p className="text-[11px] text-[#132A2E] leading-relaxed">
          Sonar can't see height directly — but every object blocks sound and casts a shadow behind it, just like sunlight. We trace that shadow's length and the sonar's known grazing angle to estimate how tall the object stands off the seafloor. Natural rock clusters cast irregular shadows; man-made debris casts a clean, geometrically consistent one — that difference filters out false positives before they ever reach the confidence score.
        </p>
      </div>
    </div>
  );
}

/* ── Tab 3: YOLO detection output ───────────────────────── */
function YoloTab({ selected, onSelect }: { selected: number | null; onSelect: (i: number | null) => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useSonarTile(ref, "yolo");

  const legend = [
    { cls: "Net",      color: "#E8604C" },
    { cls: "Pipe",     color: "#F2A94E" },
    { cls: "Cylinder", color: "#1C7C72" },
    { cls: "Shipwreck",color: "#7C9490" },
  ];

  /* Click areas relative to a 560×260 canvas */
  const boxes = [
    { i: 0, left: "30.9%", top: "36.9%", width: "12.9%", height: "13.8%" },
    { i: 1, left: "63.6%", top: "50%",   width: "10%",   height: "10.8%" },
  ];

  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="relative flex-shrink-0" style={{ borderRadius: "14px", overflow: "hidden", height: "260px" }}>
        <canvas ref={ref} width={560} height={260}
          className="w-full h-full" style={{ imageRendering: "auto" }}/>

        {/* Clickable overlay boxes */}
        {boxes.map(b => (
          <button
            key={b.i}
            onClick={() => onSelect(selected === b.i ? null : b.i)}
            className="absolute border-2 transition-opacity"
            style={{
              left: b.left, top: b.top, width: b.width, height: b.height,
              borderColor: "transparent",
              borderRadius: "1px",
              opacity: selected === null || selected === b.i ? 1 : 0.4,
            }}
          />
        ))}

        {/* Nadir */}
        <div className="absolute top-0 bottom-0 w-px bg-white/12 pointer-events-none" style={{left:"50%"}}/>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3">
        {legend.map(l => (
          <div key={l.cls} className="flex items-center gap-1.5">
            <span className="w-3 h-3 rounded-sm" style={{ background: l.color }} />
            <span className="text-[11px] text-[#7C9490]">{l.cls}</span>
          </div>
        ))}
      </div>

      {/* Logic strip */}
      <div className="bg-[#FEF4E8] p-4" style={{ borderRadius: "4px" }}>
        <div className="text-xs font-semibold text-[#0E4749] mb-1.5" style={{ fontFamily: "var(--font-display)" }}>
          Double-validated detections
        </div>
        <p className="text-[11px] text-[#132A2E] leading-relaxed">
          The cleaned tile and validated shadow measurements feed a lightweight YOLO model trained on four debris classes. Each box only survives if it clears both the model's own confidence threshold and the shadow-consistency check from the previous step — so what you see here has already been checked twice.
        </p>
      </div>
    </div>
  );
}

/* ── Dashboard page ──────────────────────────────────────── */
export default function Dashboard() {
  const [tab, setTab]       = useState<Tab>(0);
  const [selDet, setSelDet] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [edge, setEdge]     = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const TABS = ["Morphological Preprocessing", "Acoustic Shadow Analysis", "YOLO Detection Output"];
  const STAGES = ["Preprocess", "Filter", "Detect", "Geotag"];

  const runDetection = () => {
    if (running) return;
    setRunning(true);
    setProgress(0);
    let p = 0;
    timerRef.current = setInterval(() => {
      p += 1.6;
      setProgress(Math.min(p, 100));
      if (p >= 100) {
        clearInterval(timerRef.current!);
        setRunning(false);
      }
    }, 55);
  };

  useEffect(() => () => { if (timerRef.current) clearInterval(timerRef.current); }, []);

  const stageIdx = Math.min(3, Math.floor(progress / 26));

  return (
    <div className="dashboard-page page-enter" style={{ fontFamily: "var(--font-body)", height: "100vh" }}>
      <div
        className="flex-1 grid gap-3 p-3 overflow-hidden"
        style={{ gridTemplateColumns: "210px 1fr 268px", minHeight: 0 }}
      >

        {/* ── LEFT: Upload & Run ─────────────────────────── */}
        <div className="flex flex-col gap-3 overflow-auto">

          {/* Drop zone */}
          <div
            className="border-2 border-dashed border-[#1C7C72]/40 bg-[#E4F1EE] flex flex-col items-center justify-center gap-2 py-6 px-4 cursor-pointer hover:border-[#1C7C72]/70 hover:bg-[#E4F1EE]/80 transition-all"
            style={{ borderRadius: "14px" }}
          >
            <svg viewBox="0 0 36 36" className="w-9 h-9 text-[#1C7C72]" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
              <rect x="4" y="6" width="28" height="26" rx="2"/>
              <path d="M12 6V4a2 2 0 012-2h8a2 2 0 012 2v2"/>
              <path d="M18 14v10M13 19l5-5 5 5"/>
            </svg>
            <p className="text-[11px] text-center text-[#132A2E] leading-snug">
              Drop a sonar log or image tile
            </p>
            <p className="text-[10px] text-[#7C9490]">.png · .jpg · .xtf</p>
          </div>

          {/* Metadata */}
          <div
            className="bg-white border border-[#E4F1EE] p-3 flex flex-col gap-2.5"
            style={{ borderRadius: "14px" }}
          >
            <div className="text-[11px] font-semibold text-[#0E4749]" style={{ fontFamily: "var(--font-display)" }}>
              Log metadata
            </div>
            {[
              ["Vehicle ID",  "AUV-PALKBAY-02"],
              ["Track ID",    "TRK-042"],
              ["Timestamp",   "2026-09-05 14:32"],
              ["Lat / Lon",   "10.4823°N 72.634°E"],
            ].map(([label, val]) => (
              <div key={label}>
                <div className="text-[9px] text-[#7C9490] mb-0.5 uppercase tracking-wide">{label}</div>
                <div
                  className="text-[10px] text-[#132A2E] bg-[#F3FAF8] px-2 py-1.5 border border-[#E4F1EE]"
                  style={{ fontFamily: "var(--font-mono)", borderRadius: "4px" }}
                >
                  {val}
                </div>
              </div>
            ))}
          </div>

          {/* Run */}
          <button
            onClick={runDetection}
            disabled={running}
            className="w-full bg-[#0E4749] text-[#F3FAF8] text-sm py-2.5 font-semibold hover:bg-[#1C7C72] disabled:opacity-50 transition-colors"
            style={{ borderRadius: "4px" }}
          >
            {running ? "Running…" : "Run Detection"}
          </button>

          {/* Pipeline progress */}
          {(progress > 0) && (
            <div className="flex flex-col gap-2">
              <div className="w-full bg-[#E4F1EE] h-1" style={{ borderRadius: "2px" }}>
                <div
                  className="h-full bg-[#1C7C72] transition-all duration-75"
                  style={{ width: `${progress}%`, borderRadius: "2px" }}
                />
              </div>
              <div className="flex justify-between">
                {STAGES.map((s, i) => (
                  <span
                    key={s}
                    className="text-[8.5px]"
                    style={{
                      fontFamily: "var(--font-mono)",
                      color: i <= stageIdx ? "#1C7C72" : "#7C9490",
                      fontWeight: i === stageIdx ? 700 : 400,
                    }}
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Edge toggle */}
          <div className="bg-[#E4F1EE] p-3 flex items-center justify-between" style={{ borderRadius: "4px" }}>
            <div>
              <div className="text-[11px] font-medium text-[#0E4749]">{edge ? "Edge / Offline" : "Cloud-assisted"}</div>
              <div className="text-[9px] text-[#7C9490]">{edge ? "No network required" : "Enhanced models"}</div>
            </div>
            <button
              onClick={() => setEdge(!edge)}
              className={`w-9 h-5 rounded-full transition-colors ${edge ? "bg-[#1C7C72]" : "bg-[#7C9490]"}`}
            >
              <span
                className={`block w-3.5 h-3.5 bg-white rounded-full transition-transform m-0.5 shadow-sm ${edge ? "" : "translate-x-4"}`}
              />
            </button>
          </div>
        </div>

        {/* ── CENTER: Image inspection ────────────────────── */}
        <div
          className="bg-white border border-[#E4F1EE] flex flex-col overflow-hidden"
          style={{ borderRadius: "14px" }}
        >
          {/* Tab strip */}
          <div className="flex border-b border-[#E4F1EE] shrink-0">
            {TABS.map((name, i) => (
              <button
                key={name}
                onClick={() => setTab(i as Tab)}
                className={`flex-1 text-[11px] py-3 px-2 font-medium transition-colors leading-tight ${
                  tab === i
                    ? "text-[#1C7C72] border-b-2 border-[#1C7C72] -mb-px"
                    : "text-[#7C9490] hover:text-[#132A2E]"
                }`}
              >
                {name}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto p-4">
            {tab === 0 && <MorphoTab />}
            {tab === 1 && <ShadowTab />}
            {tab === 2 && <YoloTab selected={selDet} onSelect={n => { setSelDet(n); }} />}
          </div>
        </div>

        {/* ── RIGHT: Detection list ───────────────────────── */}
        <div
          className="bg-white border border-[#E4F1EE] flex flex-col overflow-hidden"
          style={{ borderRadius: "14px" }}
        >
          <div className="px-4 py-3 border-b border-[#E4F1EE] shrink-0">
            <div className="text-sm font-semibold text-[#0E4749]" style={{ fontFamily: "var(--font-display)" }}>
              Detections in this tile
            </div>
            <div className="text-[10px] text-[#7C9490]" style={{ fontFamily: "var(--font-mono)" }}>
              TRK-042 · {DETECTIONS.length} found
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {DETECTIONS.map((d, i) => (
              <button
                key={d.id}
                onClick={() => { setSelDet(i === selDet ? null : i); setTab(2); }}
                className={`w-full flex items-center gap-3 px-4 py-3 border-b border-[#E4F1EE] text-left hover:bg-[#F3FAF8] transition-colors ${
                  selDet === i ? "bg-[#E4F1EE]" : ""
                }`}
              >
                {/* Thumbnail */}
                <div
                  className="w-8 h-8 shrink-0 flex items-center justify-center"
                  style={{
                    background: d.color + "18",
                    border: `1px solid ${d.color}30`,
                    borderRadius: "4px",
                  }}
                >
                  <div className="w-3.5 h-3.5 rounded-sm" style={{ background: d.color, opacity: 0.75 }} />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-semibold text-[#132A2E] truncate">{d.cls}</div>
                  <div className="text-[9px] text-[#7C9490]" style={{ fontFamily: "var(--font-mono)" }}>
                    {d.lat} · {d.depth}
                  </div>
                </div>

                <ConfPill v={d.conf} />
              </button>
            ))}
          </div>

          {/* Mini lat/lon display for selected */}
          {selDet !== null && (
            <div className="px-4 py-3 bg-[#F3FAF8] border-t border-[#E4F1EE] shrink-0">
              <div className="text-[9px] text-[#7C9490] mb-1">Selected detection</div>
              <div className="text-[10px] text-[#132A2E]" style={{ fontFamily: "var(--font-mono)" }}>
                {DETECTIONS[selDet].lat}<br />
                {DETECTIONS[selDet].lon}<br />
                {DETECTIONS[selDet].depth}
              </div>
            </div>
          )}

          <div className="p-4 border-t border-[#E4F1EE] shrink-0">
            <button
              className="w-full text-[11px] bg-[#E4F1EE] text-[#0E4749] py-2 font-semibold hover:bg-[#1C7C72] hover:text-white transition-colors"
              style={{ borderRadius: "4px" }}
            >
              Send all to report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
