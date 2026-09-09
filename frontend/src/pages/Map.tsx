import { useState } from "react";

/* ────────────────────────────────────────────────────────────
   DATA
──────────────────────────────────────────────────────────── */

const DETECTIONS = [
  { id: "DET-001", cls: "Entangled Net", conf: 91, lat: 10.4823, lon: 72.6341, depth: "28 m", svgX: 252, svgY: 218 },
  { id: "DET-002", cls: "Steel Pipe",    conf: 76, lat: 10.4819, lon: 72.6338, depth: "29 m", svgX: 365, svgY: 195 },
  { id: "DET-003", cls: "Cylinder",      conf: 61, lat: 10.4815, lon: 72.633,  depth: "31 m", svgX: 468, svgY: 178 },
  { id: "DET-004", cls: "Entangled Net", conf: 84, lat: 10.481,  lon: 72.6325, depth: "27 m", svgX: 572, svgY: 162 },
  { id: "DET-005", cls: "Shipwreck",     conf: 95, lat: 10.4806, lon: 72.6318, depth: "34 m", svgX: 680, svgY: 148 },
  { id: "DET-006", cls: "Cylinder",      conf: 72, lat: 10.4802, lon: 72.6312, depth: "36 m", svgX: 782, svgY: 136 },
];

const CLASS_COLORS: Record<string, string> = {
  "Entangled Net": "#F0533D",
  "Steel Pipe":    "#F5A93F",
  "Cylinder":      "#20C4B0",
  "Shipwreck":     "#8FA6AE",
};

/* Shared theme tokens for the console + light sections */
const THEME = {
  deepNavy:  "#050F16",
  navy:      "#0A1E29",
  navyMid:   "#0F2C3B",
  navyLine:  "#123645",
  teal:      "#14B8A6",
  tealSoft:  "#5EEAD4",
  ink:       "#0A2540",
  lightBg:   "#F4FAF9",
  card:      "#FFFFFF",
  border:    "#DCEEEA",
  muted:     "#5B7A80",
};

/* ────────────────────────────────────────────────────────────
   COMPONENT
──────────────────────────────────────────────────────────── */

export default function MapPage() {
  const [selected,      setSelected]      = useState<string | null>(null);
  const [threshold,     setThreshold]     = useState(0);
  const [activeClasses, setActiveClasses] = useState(new Set(Object.keys(CLASS_COLORS)));
  const [viewMode,      setViewMode]      = useState<"pins" | "heatmap">("pins");

  const toggle = (cls: string) => {
    const n = new Set(activeClasses);
    n.has(cls) ? n.delete(cls) : n.add(cls);
    setActiveClasses(n);
  };

  const visible = DETECTIONS.filter(d => d.conf >= threshold && activeClasses.has(d.cls));
  const selDet  = selected ? DETECTIONS.find(d => d.id === selected) : null;

  /* Aggregate stats per class for the summary table */
  const classStats = Object.keys(CLASS_COLORS).map(cls => {
    const items = DETECTIONS.filter(d => d.cls === cls);
    const count = items.length;
    const avgConf = count ? Math.round(items.reduce((s, d) => s + d.conf, 0) / count) : 0;
    const maxConf = count ? Math.max(...items.map(d => d.conf)) : 0;
    const share = Math.round((count / DETECTIONS.length) * 100);
    return { cls, count, avgConf, maxConf, share };
  }).sort((a, b) => b.count - a.count);

  return (
    <div className="map-page page-enter" style={{ fontFamily: "var(--font-body)" }}>
      <style>{`
        @keyframes pinPulse {
          0%   { transform: scale(1);   opacity: 0.55; }
          70%  { transform: scale(2.4); opacity: 0;    }
          100% { transform: scale(2.4); opacity: 0;    }
        }
        @keyframes sweepRotate {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        .pin-ring {
          transform-origin: center;
          transform-box: fill-box;
          animation: pinPulse 2.6s ease-out infinite;
        }
        .sweep-wedge {
          transform-origin: 512px 290px;
          transform-box: view-box;
          animation: sweepRotate 9s linear infinite;
        }
      `}</style>

      {/* ══════════════════════════════════════════════════
          SECTION 1 — SONAR CONFIDENCE CONSOLE
      ══════════════════════════════════════════════════ */}
      <div className="relative w-full" style={{ background: THEME.deepNavy }}>

        {/* Status strip */}
        <div
          className="flex items-center justify-between px-4 py-2 text-[10px]"
          style={{
            background: THEME.navy,
            borderBottom: `1px solid ${THEME.navyLine}`,
            fontFamily: "var(--font-mono)",
            color: THEME.tealSoft,
          }}
        >
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ background: "#3DDC84", boxShadow: "0 0 6px #3DDC84" }}
              />
              LIVE SONAR FEED
            </span>
            <span style={{ color: THEME.muted }}>AUV-07</span>
            <span style={{ color: THEME.muted }}>DEPTH 31 m</span>
          </div>
          <div className="flex items-center gap-4" style={{ color: THEME.muted }}>
            <span>SURVEY PROGRESS</span>
            <div className="w-24 h-1 rounded-full overflow-hidden" style={{ background: THEME.navyLine }}>
              <div className="h-full" style={{ width: "68%", background: THEME.teal }} />
            </div>
            <span style={{ color: THEME.tealSoft }}>68%</span>
          </div>
        </div>

        {/* Map canvas */}
        <div className="relative" style={{ height: "580px" }}>
          <svg viewBox="0 0 1024 580" className="w-full h-full" preserveAspectRatio="xMidYMid slice" fill="none">
            <defs>
              <linearGradient id="seabed" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"  stopColor="#0B222E" />
                <stop offset="100%" stopColor="#040D12" />
              </linearGradient>
              <radialGradient id="glow" cx="35%" cy="70%" r="55%">
                <stop offset="0%"  stopColor="#123A45" stopOpacity="0.5" />
                <stop offset="100%" stopColor="transparent" />
              </radialGradient>
              <linearGradient id="sweepGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%"   stopColor={THEME.teal} stopOpacity="0" />
                <stop offset="100%" stopColor={THEME.teal} stopOpacity="0.16" />
              </linearGradient>
            </defs>

            <rect width="1024" height="580" fill="url(#seabed)" />
            <rect width="1024" height="580" fill="url(#glow)" />

            {/* Bathymetric contours */}
            {[0, 1, 2, 3, 4].map(i => (
              <path
                key={i}
                d={`M0 ${200 + i * 48} Q256 ${182 + i * 46} 512 ${196 + i * 50} Q768 ${210 + i * 47} 1024 ${188 + i * 49}`}
                stroke={THEME.teal}
                strokeWidth="0.7"
                opacity={0.08 + i * 0.02}
                fill="none"
              />
            ))}

            {/* Grid */}
            {[128, 256, 384, 512, 640, 768, 896].map(x => (
              <line key={x} x1={x} y1="0" x2={x} y2="580" stroke={THEME.teal} strokeWidth="0.4" opacity="0.07" />
            ))}
            {[116, 232, 348, 464].map(y => (
              <line key={y} x1="0" y1={y} x2="1024" y2={y} stroke={THEME.teal} strokeWidth="0.4" opacity="0.07" />
            ))}

            {/* Sonar sweep wedge */}
            <g className="sweep-wedge" opacity="0.5">
              <path d="M512 290 L512 40 A250 250 0 0 1 720 130 Z" fill="url(#sweepGrad)" />
            </g>

            {/* Landmasses */}
            <path d="M0 0 L240 0 L240 108 Q195 148 130 140 Q65 132 0 168Z" fill="#132D38" />
            <path d="M0 0 L240 0 L240 108 Q195 148 130 140 Q65 132 0 168Z" stroke={THEME.navyLine} strokeWidth="1" />
            <path d="M880 520 L1024 520 L1024 580 L880 580Z" fill="#132D38" opacity="0.8" />
            <path d="M840 565 Q900 548 980 558 L980 580 L840 580Z" fill="#132D38" opacity="0.6" />

            {/* Coordinate labels */}
            <text x="8" y="575" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.55">10.47°N</text>
            <text x="8" y="210" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.55">10.49°N</text>
            <text x="210" y="575" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.55">72.62°E</text>
            <text x="730" y="575" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.55">72.64°E</text>

            {/* Survey track */}
            <path
              d="M160 360 Q228 305 320 256 Q412 207 510 192 Q608 177 706 160 Q780 147 862 132"
              stroke={THEME.teal}
              strokeWidth="2"
              strokeDasharray="10,5"
              opacity="0.65"
            />
            <circle cx="160" cy="360" r="7" fill={THEME.teal} opacity="0.2" />
            <circle cx="160" cy="360" r="4" fill={THEME.teal} opacity="0.8" />
            <text x="170" y="365" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.8">Start</text>
            <circle cx="862" cy="132" r="4" fill={THEME.teal} opacity="0.7" />
            <text x="870" y="136" fill={THEME.tealSoft} fontSize="9" fontFamily="IBM Plex Mono" opacity="0.7">End</text>

            {/* Heatmap mode */}
            {viewMode === "heatmap" && visible.map(d => (
              <circle key={d.id} cx={d.svgX} cy={d.svgY} r={d.conf * 0.6} fill={CLASS_COLORS[d.cls]} opacity="0.14" />
            ))}

            {/* Pins */}
            {viewMode === "pins" && visible.map(d => {
              const color = CLASS_COLORS[d.cls];
              const r = d.conf >= 90 ? 9 : d.conf >= 70 ? 7 : 5.5;
              const isSel = selected === d.id;
              return (
                <g key={d.id} onClick={() => setSelected(isSel ? null : d.id)} style={{ cursor: "pointer" }}>
                  <circle className="pin-ring" cx={d.svgX} cy={d.svgY} r={r} fill={color} />
                  {isSel && <circle cx={d.svgX} cy={d.svgY} r={r + 12} fill={color} opacity="0.16" />}
                  <circle cx={d.svgX} cy={d.svgY} r={r + 4} fill={color} opacity="0.18" />
                  <circle cx={d.svgX} cy={d.svgY} r={r} fill={color} stroke="#04141A" strokeWidth="1.2" />
                  <text
                    x={d.svgX} y={d.svgY - r - 6}
                    textAnchor="middle"
                    fill={THEME.tealSoft}
                    fontSize="8"
                    fontFamily="IBM Plex Mono"
                    fontWeight="600"
                  >
                    {d.conf}%
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Filter panel */}
          <div
            className="absolute left-4 top-4 flex flex-col gap-4 p-4 backdrop-blur"
            style={{
              width: "220px",
              borderRadius: "14px",
              background: "rgba(15,44,59,0.82)",
              border: `1px solid ${THEME.navyLine}`,
            }}
          >
            <div className="text-sm font-semibold" style={{ color: "#EAF6F4", fontFamily: "var(--font-display)" }}>
              Filter detections
            </div>

            <div>
              <div className="flex justify-between mb-1.5">
                <span className="text-[11px]" style={{ color: "#B7CBCF" }}>Confidence ≥</span>
                <span className="text-[11px] font-semibold" style={{ color: THEME.tealSoft, fontFamily: "var(--font-mono)" }}>
                  {threshold}%
                </span>
              </div>
              <input
                type="range" min={0} max={100} value={threshold}
                onChange={e => setThreshold(Number(e.target.value))}
                className="w-full h-1.5"
                style={{ accentColor: THEME.teal }}
              />
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide mb-2" style={{ color: THEME.muted }}>Class</div>
              {Object.keys(CLASS_COLORS).map(cls => (
                <label key={cls} className="flex items-center gap-2 mb-2 cursor-pointer">
                  <input
                    type="checkbox" checked={activeClasses.has(cls)} onChange={() => toggle(cls)}
                    style={{ accentColor: THEME.teal }}
                  />
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: CLASS_COLORS[cls] }} />
                  <span className="text-[11px]" style={{ color: "#D6E7E5" }}>{cls}</span>
                </label>
              ))}
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: THEME.muted }}>View</div>
              <div className="flex rounded overflow-hidden" style={{ border: `1px solid ${THEME.navyLine}` }}>
                {(["pins", "heatmap"] as const).map(m => (
                  <button
                    key={m}
                    onClick={() => setViewMode(m)}
                    className="flex-1 text-[11px] py-1.5 capitalize transition-colors"
                    style={{
                      background: viewMode === m ? THEME.teal : "transparent",
                      color: viewMode === m ? "#04141A" : THEME.muted,
                    }}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Selection popup */}
          {selDet && (
            <div
              className="absolute p-4 backdrop-blur"
              style={{
                width: "240px",
                left: "252px", top: "16px",
                borderRadius: "14px",
                background: "rgba(15,44,59,0.94)",
                border: `1px solid ${THEME.navyLine}`,
                boxShadow: "0 12px 32px rgba(0,0,0,0.4)",
              }}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div className="text-sm font-semibold" style={{ color: "#EAF6F4", fontFamily: "var(--font-display)" }}>
                    {selDet.cls}
                  </div>
                  <div className="text-[10px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                    {selDet.id}
                  </div>
                </div>
                <button
                  onClick={() => setSelected(null)}
                  className="text-xl leading-none mt-0.5"
                  style={{ color: THEME.muted }}
                >
                  ×
                </button>
              </div>

              <div className="space-y-2">
                {[
                  { l: "Confidence", v: selDet.conf + "%", accent: true },
                  { l: "Latitude",   v: selDet.lat.toFixed(4) + "°N" },
                  { l: "Longitude",  v: selDet.lon.toFixed(4) + "°E" },
                  { l: "Depth",      v: selDet.depth },
                ].map(row => (
                  <div key={row.l} className="flex justify-between items-center">
                    <span className="text-[10px]" style={{ color: THEME.muted }}>{row.l}</span>
                    {row.accent ? (
                      <span
                        className="text-[10px] font-semibold px-2 py-0.5"
                        style={{
                          background: CLASS_COLORS[selDet.cls],
                          color: "#04141A",
                          borderRadius: "4px",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {row.v}
                      </span>
                    ) : (
                      <span className="text-[10px]" style={{ color: "#D6E7E5", fontFamily: "var(--font-mono)" }}>
                        {row.v}
                      </span>
                    )}
                  </div>
                ))}
              </div>

              <button
                className="mt-3 w-full text-[11px] py-1.5 font-medium transition-colors"
                style={{
                  borderRadius: "4px",
                  border: `1px solid ${THEME.teal}66`,
                  color: THEME.tealSoft,
                }}
              >
                View full tile
              </button>
            </div>
          )}

          {/* Legend */}
          <div
            className="absolute bottom-6 left-4 p-3 backdrop-blur"
            style={{ borderRadius: "14px", background: "rgba(15,44,59,0.82)", border: `1px solid ${THEME.navyLine}` }}
          >
            <div className="text-[9px] uppercase tracking-wide mb-2" style={{ color: THEME.muted }}>Class legend</div>
            {Object.entries(CLASS_COLORS).map(([cls, color]) => (
              <div key={cls} className="flex items-center gap-2 mb-1.5 last:mb-0">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: color }} />
                <span className="text-[10px]" style={{ color: "#D6E7E5" }}>{cls}</span>
              </div>
            ))}
            <div className="mt-2 pt-2 text-[9px]" style={{ borderTop: `1px solid ${THEME.navyLine}`, color: THEME.muted }}>
              {visible.length} / {DETECTIONS.length} shown
            </div>
          </div>

          {/* Export button */}
          <div className="absolute top-4 right-4">
            <button
              className="text-sm px-4 py-2.5 font-semibold transition-colors"
              style={{ background: THEME.teal, color: "#04141A", borderRadius: "4px" }}
            >
              Export visible detections
            </button>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════
          SECTION 2 — THREE-STAGE VISUAL ANALYSIS
      ══════════════════════════════════════════════════ */}
      <section className="page-shell" style={{ background: THEME.lightBg, padding: "64px 24px" }} aria-labelledby="stage-title">
        <div className="mb-8">
          <p className="eyebrow flex items-center gap-2" style={{ color: THEME.teal }}>
            <span style={{ width: "18px", height: "2px", background: THEME.teal, display: "inline-block" }} />
            ANALYSIS VIEWS
          </p>
          <h1 id="stage-title" style={{ color: THEME.ink, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "28px", margin: "6px 0" }}>
            THREE-STAGE <span style={{ color: THEME.teal }}>VISUAL ANALYSIS</span>
          </h1>
          <p style={{ color: THEME.muted, maxWidth: "560px", fontSize: "14px" }}>
            Every geotagged target is validated through morphology, acoustic shadow geometry, and dual-model
            detection before it reaches the map.
          </p>
        </div>

        <div
          className="grid gap-5"
          style={{ gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}
        >
          {/* ── Panel 1: Morphological output ── */}
          <StagePanel
            caption="MORPHOLOGICAL OUTPUT"
            captionColor={THEME.tealSoft}
            title="Morphological preprocessing"
            desc="Speckle noise removed — object outline preserved"
            src="/morph.jpg"
            alt="Morphological preprocessing output"
          />

          {/* ── Panel 2: Acoustic shadow analysis ── */}
          <StagePanel
            caption="ACOUSTIC SHADOW ANALYSIS"
            captionColor="#7DD3FC"
            title="Acoustic shadow analysis"
            desc="Height estimated from shadow geometry + grazing angle"
            src="/acous.jpg"
            alt="Acoustic shadow analysis output"
          />

          {/* ── Panel 3: YOLO detection output ── */}
          <StagePanel
            caption="YOLO DETECTION OUTPUT"
            captionColor="#FBBF6B"
            title="YOLO detection output"
            desc="Dual-validated bounding boxes with confidence scores"
            src="/yolo.jpg"
            alt="YOLO detection output"
          />
        </div>
      </section>

      {/* ══════════════════════════════════════════════════
          SECTION 3 — DETECTION SUMMARY TABLE
      ══════════════════════════════════════════════════ */}
      <section
        className="page-shell"
        style={{ background: THEME.card, padding: "64px 24px 80px", borderTop: `1px solid ${THEME.border}` }}
        aria-labelledby="summary-title"
      >
        <div className="mb-8 flex items-start justify-between flex-wrap gap-4">
          <div>
            <p className="eyebrow flex items-center gap-2" style={{ color: THEME.teal }}>
              <span style={{ width: "18px", height: "2px", background: THEME.teal, display: "inline-block" }} />
              MISSION SUMMARY
            </p>
            <h2
              id="summary-title"
              style={{ color: THEME.ink, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "26px", margin: "6px 0" }}
            >
              DETECTION <span style={{ color: THEME.teal }}>BREAKDOWN</span>
            </h2>
            <p style={{ color: THEME.muted, maxWidth: "560px", fontSize: "14px" }}>
              Live tally of how many targets of each class were flagged this survey, with average and
              peak model confidence per class.
            </p>
          </div>
          <div
            className="flex items-center gap-3 px-4 py-2.5"
            style={{ background: THEME.lightBg, border: `1px solid ${THEME.border}`, borderRadius: "8px" }}
          >
            <span className="text-[11px]" style={{ color: THEME.muted }}>Total detections</span>
            <span
              className="text-lg font-bold"
              style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}
            >
              {DETECTIONS.length}
            </span>
          </div>
        </div>

        <div
          style={{
            border: `1px solid ${THEME.border}`,
            borderRadius: "12px",
            overflow: "hidden",
            boxShadow: "0 4px 16px rgba(10,37,64,0.05)",
          }}
        >
          <table className="w-full border-collapse" style={{ fontFamily: "var(--font-body)" }}>
            <thead>
              <tr style={{ background: THEME.ink }}>
                {["Class", "Count", "Share of total", "Avg. confidence", "Peak confidence"].map((h, i) => (
                  <th
                    key={h}
                    className="text-left px-5 py-3"
                    style={{
                      color: "#EAF6F4",
                      fontSize: "10px",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                      fontFamily: "var(--font-mono)",
                      textAlign: i === 0 ? "left" : "left",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {classStats.map((row, i) => (
                <tr
                  key={row.cls}
                  style={{
                    background: i % 2 === 0 ? THEME.card : THEME.lightBg,
                    borderTop: `1px solid ${THEME.border}`,
                  }}
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2.5">
                      <span
                        className="w-2.5 h-2.5 rounded-sm shrink-0"
                        style={{ background: CLASS_COLORS[row.cls] }}
                      />
                      <span className="text-[13px] font-semibold" style={{ color: THEME.ink }}>
                        {row.cls}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-[13px] font-semibold" style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}>
                      {row.count}
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3" style={{ minWidth: "160px" }}>
                      <div
                        className="h-1.5 rounded-full overflow-hidden flex-1"
                        style={{ background: THEME.border, maxWidth: "120px" }}
                      >
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${row.share}%`, background: CLASS_COLORS[row.cls] }}
                        />
                      </div>
                      <span className="text-[12px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                        {row.share}%
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className="text-[11px] font-semibold px-2 py-1"
                      style={{
                        background: `${CLASS_COLORS[row.cls]}1A`,
                        color: CLASS_COLORS[row.cls],
                        borderRadius: "4px",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {row.avgConf}%
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span className="text-[13px]" style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}>
                      {row.maxConf}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: `2px solid ${THEME.border}`, background: THEME.lightBg }}>
                <td className="px-5 py-3 text-[11px] font-semibold" style={{ color: THEME.muted }}>Total</td>
                <td className="px-5 py-3 text-[13px] font-bold" style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}>
                  {DETECTIONS.length}
                </td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted }}>100%</td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                  {Math.round(DETECTIONS.reduce((s, d) => s + d.conf, 0) / DETECTIONS.length)}% avg
                </td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                  {Math.max(...DETECTIONS.map(d => d.conf))}% max
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   Reusable panel wrapper for section 2
──────────────────────────────────────────────────────────── */
function StagePanel({
  caption, captionColor, title, desc, src, alt,
}: {
  caption: string;
  captionColor: string;
  title: string;
  desc: string;
  src: string;
  alt: string;
}) {
  return (
    <div>
      <div
        className="relative w-full overflow-hidden"
        style={{
          aspectRatio: "300 / 190",
          borderRadius: "10px",
          border: `1px solid ${THEME.border}`,
          boxShadow: "0 4px 16px rgba(10,37,64,0.06)",
          background: "#050D12",
        }}
      >
        <img src={src} alt={alt} className="w-full h-full object-cover" />
        <span
          className="absolute bottom-2 left-2 text-[9px] font-semibold tracking-wide px-1.5 py-0.5"
          style={{ color: captionColor, fontFamily: "IBM Plex Mono", background: "rgba(5,13,18,0.6)", borderRadius: "3px" }}
        >
          {caption}
        </span>
      </div>
      <div className="mt-3">
        <div
          className="text-[11px] font-bold tracking-wide"
          style={{ color: THEME.ink, fontFamily: "var(--font-display)" }}
        >
          {title.toUpperCase()}
        </div>
        <p className="text-[12px] mt-1" style={{ color: THEME.muted }}>{desc}</p>
      </div>
    </div>
  );
}