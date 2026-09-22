import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { MapContainer, TileLayer, WMSTileLayer, CircleMarker, Marker, Tooltip, ZoomControl, useMap, useMapEvent } from "react-leaflet";
import L, { type LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import { createTargetPinIcon } from "../utils/mapPins";
import { Upload, Crosshair, Loader2, Download } from "lucide-react";
import {
  analyzeSonarImage,
  clampVesselField,
  downloadAnalysisReport,
  resolveApiAssetUrl,
  type AnalysisTarget,
  type MasterAnalysisResult,
  type VesselParams,
} from "../api/client";

/* ────────────────────────────────────────────────────────────
   REAL PROJECT CLASSES
   The 7 classes the trained YOLO11 model actually outputs (see
   backend/app/ml/class_map.py — CLASS_MAP). Colours are copied
   directly from that file's color_hex so the map and the backend
   agree on what each class looks like.
──────────────────────────────────────────────────────────── */
const CLASS_META: Record<string, { label: string; color: string }> = {
  shipwreck: { label: "Shipwreck", color: "#E63946" },
  pipe: { label: "Subsea Pipeline / Pipe", color: "#F4A261" },
  ghost_net: { label: "Entangled / Ghost Net", color: "#E76F51" },
  marine_debris: { label: "Marine Debris / Container", color: "#E9C46A" },
  aircraft: { label: "Aircraft Wreckage", color: "#D62828" },
  other: { label: "Unidentified Target", color: "#457B9D" },
  fish: { label: "Marine Organism", color: "#2A9D8F" },
};

const KNOWN_CLASSES = Object.keys(CLASS_META);

const classColor = (cls: string): string => CLASS_META[cls]?.color ?? "#8FA6AE";
const classLabel = (t: { class_name: string; display_name?: string }): string =>
  t.display_name || CLASS_META[t.class_name]?.label || t.class_name;

/* Shared theme tokens for the console + light sections (unchanged design). */
const THEME = {
  deepNavy: "#050F16",
  navy: "#0A1E29",
  navyLine: "#123645",
  teal: "#14B8A6",
  tealSoft: "#5EEAD4",
  ink: "#0A2540",
  lightBg: "#F4FAF9",
  card: "#FFFFFF",
  border: "#DCEEEA",
  muted: "#5B7A80",
};

/* A real Bay-of-Bengal point off Chennai. 13.05,80.28 is on land — 80.42 is water. */
const DEFAULT_VESSEL: VesselParams = { vesselLat: 13.05, vesselLon: 80.42, vesselHeadingDeg: 90 };

/* Official GEBCO depth-colour legend, fetched directly from INCOIS's own
   GeoServer (GetLegendGraphic) — the exact colour ramp for the bathymetry
   layer below, not something we drew ourselves. The JSON variant returns the
   real colour stops + depth values as data (no baked-in raster text), which
   lets us render our own dark-theme-legible legend from real numbers instead
   of embedding INCOIS's white-background PNG. */
const INCOIS_LEGEND_JSON_URL =
  "https://incois.gov.in/geoserver/BathymteryImage/wms?SERVICE=WMS&VERSION=1.1.0&REQUEST=GetLegendGraphic&LAYER=BathymteryImage:gebcobathymtery&FORMAT=application/json";

interface DepthStop {
  quantity: number;
  color: string;
}

async function fetchDepthLegend(): Promise<DepthStop[]> {
  const res = await fetch(INCOIS_LEGEND_JSON_URL);
  if (!res.ok) throw new Error(`legend fetch failed: ${res.status}`);
  const data = await res.json();
  const entries = data?.Legend?.[0]?.rules?.[0]?.symbolizers?.[0]?.Raster?.colormap?.entries ?? [];
  return entries.map((e: { quantity: string; color: string }) => ({
    quantity: Number(e.quantity),
    color: e.color,
  }));
}

/* ────────────────────────────────────────────────────────────
   Flattened, map-ready view of a backend target.
──────────────────────────────────────────────────────────── */
interface MapDetection {
  id: string;
  cls: string;
  label: string;
  conf: number; // 0..100
  lat: number;
  lon: number;
  riskTier: string;
  lengthM: number;
  heightM: number;
}

function toDetections(targets: AnalysisTarget[]): MapDetection[] {
  return targets
    .filter((t): t is AnalysisTarget & { coordinates: { latitude: number; longitude: number } } =>
      t.coordinates != null && typeof t.coordinates.latitude === 'number' && typeof t.coordinates.longitude === 'number'
    )
    .map((t) => ({
      id: t.detection_id,
      cls: t.class_name,
      label: classLabel(t),
      conf: Math.round((t.calibrated_confidence ?? 0) * 100),
      lat: t.coordinates.latitude,
      lon: t.coordinates.longitude,
      riskTier: t.risk_tier,
      lengthM: t.dimensions?.length_m ?? 0,
      heightM: t.dimensions?.height_m ?? 0,
    }));
}

/* ────────────────────────────────────────────────────────────
   Fit the Leaflet view to whatever real points exist.
──────────────────────────────────────────────────────────── */
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const appliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (points.length === 0) return;
    const key = JSON.stringify(points);
    if (appliedRef.current === key) return;
    appliedRef.current = key;

    if (points.length === 1) {
      map.setView(points[0], 13);
      return;
    }

    // Leaflet's fitBounds can zoom out to a near-whole-world view when the
    // bounding box is degenerate (all points within meters of each other —
    // e.g. a single close-range detection right next to the vessel). Detect
    // that case and just center on it at a sensible fixed zoom instead.
    const bounds = L.latLngBounds(points);
    const span = Math.max(
      bounds.getNorth() - bounds.getSouth(),
      bounds.getEast() - bounds.getWest()
    );
    const DEGENERATE_SPAN_DEG = 0.01; // ~1km at these latitudes

    if (span < DEGENERATE_SPAN_DEG) {
      map.setView(bounds.getCenter(), 15);
    } else {
      map.fitBounds(bounds as LatLngBoundsExpression, { padding: [40, 40], maxZoom: 16 });
    }
  }, [points, map]);

  return null;
}

/* ────────────────────────────────────────────────────────────
   Live cursor coordinate readout — the actual lat/lon under the
   mouse, updated on real Leaflet mousemove events. Answers
   "where am I actually pointing" without needing to click a pin.

   A native mousemove fires 60-100+ times/sec while panning; calling
   setState on every one of those was the main source of the map
   feeling laggy. Throttled to ~20 updates/sec (50ms) via a ref-held
   timestamp — frequent enough to feel live, rare enough not to
   flood React's render cycle.
──────────────────────────────────────────────────────────── */
function CursorReadout() {
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);
  const lastUpdate = useRef(0);

  useMapEvent("mousemove", (e) => {
    const now = performance.now();
    if (now - lastUpdate.current < 50) return;
    lastUpdate.current = now;
    setPos(e.latlng);
  });
  useMapEvent("mouseout", () => setPos(null));

  return (
    <div
      className="absolute bottom-3 right-3 z-[500] px-2.5 py-1"
      style={{
        borderRadius: "6px",
        background: "rgba(10,30,41,0.82)",
        border: "1px solid #123645",
        color: "#5EEAD4",
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        pointerEvents: "none",
      }}
    >
      {pos ? `${pos.lat.toFixed(5)}°, ${pos.lng.toFixed(5)}°` : "move over map for coordinates"}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────
   The real map: OpenStreetMap base + INCOIS bathymetry overlay +
   real detection markers + sensor marker. No fake data anywhere.
──────────────────────────────────────────────────────────── */
function DetectionMap({
  detections,
  vessel,
  viewMode,
  selected,
  onSelect,
}: {
  detections: MapDetection[];
  vessel: VesselParams;
  viewMode: "pins" | "heatmap";
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const points: [number, number][] = detections.map((d) => [d.lat, d.lon]);
  points.push([vessel.vesselLat, vessel.vesselLon]);

  return (
    <MapContainer
      center={[vessel.vesselLat, vessel.vesselLon]}
      zoom={13}
      scrollWheelZoom
      zoomControl={false}
      style={{ height: "100%", width: "100%", background: THEME.deepNavy }}
    >
      {/* Leaflet's default zoom control sits top-left, the same corner as
          the Filter panel — moved to bottom-left (empty since the separate
          Class-legend panel was folded into Filter) so they don't overlap. */}
      <ZoomControl position="bottomleft" />
      {/* Reliable base layer — always renders even if INCOIS is unreachable. */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {/* Real seafloor bathymetry from INCOIS's public GeoServer, layered
          semi-transparently on top. Undocumented government endpoint — if it is
          ever down the tiles just render blank and the base map still shows.
          updateWhenIdle/updateWhenZooming=false stop it firing a fresh batch of
          tile requests on every intermediate frame of a drag or zoom — INCOIS's
          server renders each tile on demand and is slow, so without this the
          map feels laggy while panning as it waits on a flood of stale requests. */}
      <WMSTileLayer
        url="https://incois.gov.in/geoserver/BathymteryImage/wms"
        layers="BathymteryImage:gebcobathymtery"
        format="image/png"
        transparent
        opacity={0.55}
        attribution="Bathymetry: INCOIS"
        updateWhenIdle
        updateWhenZooming={false}
        keepBuffer={4}
      />

      {detections.map((d, i) => {
        const color = classColor(d.cls);
        const isSel = selected === d.id;
        // In heatmap mode each target becomes a large translucent blob whose
        // size scales with confidence — a real spatial density read, not an SVG trick.
        if (viewMode === "heatmap") {
          const radius = 14 + d.conf * 0.22;
          return (
            <CircleMarker
              key={d.id}
              center={[d.lat, d.lon]}
              radius={radius}
              pathOptions={{
                color,
                weight: isSel ? 3 : 2,
                fillColor: color,
                fillOpacity: 0.35,
              }}
              eventHandlers={{ click: () => onSelect(isSel ? null : d.id) }}
            >
              <Tooltip direction="top" offset={[0, -radius]} opacity={1}>
                {d.label} · {d.conf}%
                <br />
                {d.lat.toFixed(5)}°, {d.lon.toFixed(5)}°
              </Tooltip>
            </CircleMarker>
          );
        }

        const pinIcon = createTargetPinIcon(color, isSel, i + 1);
        return (
          <Marker
            key={d.id}
            position={[d.lat, d.lon]}
            icon={pinIcon}
            zIndexOffset={isSel ? 1000 : 100}
            eventHandlers={{ click: () => onSelect(isSel ? null : d.id) }}
          >
            <Tooltip direction="top" offset={[0, isSel ? -42 : -34]} opacity={1}>
              #{i + 1} {d.label} · {d.conf}%
              <br />
              {d.lat.toFixed(5)}°, {d.lon.toFixed(5)}°
            </Tooltip>
          </Marker>
        );
      })}

      {/* Vessel / sensor position (green), from the real coordinates entered. */}
      <CircleMarker
        center={[vessel.vesselLat, vessel.vesselLon]}
        radius={7}
        pathOptions={{ color: "#16a34a", weight: 3, fillColor: "#16a34a", fillOpacity: 0.9 }}
      >
        <Tooltip direction="top" offset={[0, -7]} opacity={1}>
          Vessel / sensor
          <br />
          {vessel.vesselLat.toFixed(5)}°, {vessel.vesselLon.toFixed(5)}°
        </Tooltip>
      </CircleMarker>

      <FitBounds points={points} />
      <CursorReadout />
    </MapContainer>
  );
}

/* ────────────────────────────────────────────────────────────
   PAGE
──────────────────────────────────────────────────────────── */
export default function MapPage() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<MasterAnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const [vessel, setVessel] = useState<VesselParams>(DEFAULT_VESSEL);

  const [selected, setSelected] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0);
  const [activeClasses, setActiveClasses] = useState(new Set(KNOWN_CLASSES));
  const [viewMode, setViewMode] = useState<"pins" | "heatmap">("pins");
  const [depthStops, setDepthStops] = useState<DepthStop[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDepthLegend()
      .then((stops) => { if (!cancelled) setDepthStops(stops); })
      .catch(() => { /* legend widget just hides itself below if this stays null */ });
    return () => { cancelled = true; };
  }, []);

  const detections = useMemo(() => toDetections(analysis?.targets ?? []), [analysis]);
  const visible = detections.filter((d) => d.conf >= threshold && activeClasses.has(d.cls));
  const selDet = selected ? detections.find((d) => d.id === selected) ?? null : null;
  const predictionImageUrl = resolveApiAssetUrl(analysis?.prediction_image_url);

  const toggle = (cls: string) => {
    setActiveClasses((prev) => {
      const n = new Set(prev);
      n.has(cls) ? n.delete(cls) : n.add(cls);
      return n;
    });
  };

  const runAnalysis = (f: File) => {
    setFile(f);
    setAnalysis(null);
    setSelected(null);
    setError(null);
    setIsAnalyzing(true);
    analyzeSonarImage(f, vessel)
      .then(setAnalysis)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsAnalyzing(false));
  };

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    // Reset so picking the exact same file again (e.g. re-running the same
    // frame after changing the vessel fix) still fires a change event —
    // browsers don't fire `change` if the file list didn't change.
    e.target.value = "";
    if (f) runAnalysis(f);
  };

  const handleExport = async () => {
    if (!file) return;
    setIsExporting(true);
    try {
      await downloadAnalysisReport(file, "csv", vessel);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report export failed");
    } finally {
      setIsExporting(false);
    }
  };

  /* Aggregate stats per class, from real detections. */
  const classStats = KNOWN_CLASSES.map((cls) => {
    const items = detections.filter((d) => d.cls === cls);
    const count = items.length;
    const avgConf = count ? Math.round(items.reduce((s, d) => s + d.conf, 0) / count) : 0;
    const maxConf = count ? Math.max(...items.map((d) => d.conf)) : 0;
    const share = detections.length ? Math.round((count / detections.length) * 100) : 0;
    return { cls, count, avgConf, maxConf, share };
  }).sort((a, b) => b.count - a.count);

  const totalAvg = detections.length
    ? Math.round(detections.reduce((s, d) => s + d.conf, 0) / detections.length)
    : 0;
  const totalMax = detections.length ? Math.max(...detections.map((d) => d.conf)) : 0;

  return (
    <div className="map-page page-enter" style={{ fontFamily: "var(--font-body)" }}>
      {/* ══════════════════════════════════════════════════
          SECTION 1 — REAL SURVEY MAP
      ══════════════════════════════════════════════════ */}
      <div className="relative w-full" style={{ background: THEME.deepNavy }}>
        {/* Control strip — real inputs that drive the real backend. */}
        <div
          className="flex flex-wrap items-center gap-4 px-4 py-2.5 text-[11px]"
          style={{
            background: THEME.navy,
            borderBottom: `1px solid ${THEME.navyLine}`,
            fontFamily: "var(--font-mono)",
            color: THEME.tealSoft,
          }}
        >
          <span className="flex items-center gap-1.5" style={{ color: THEME.tealSoft }}>
            <Crosshair size={13} /> SURVEY MAP
          </span>

          <label className="flex items-center gap-1.5" style={{ color: THEME.muted }}>
            LAT
            <input
              type="number"
              step="0.0001"
              min={-90}
              max={90}
              value={vessel.vesselLat}
              // Clamp to a physically valid latitude — an out-of-range value
              // (e.g. a stray extra digit) reaches the backend as a 400 and
              // also breaks Leaflet's own rendering (map goes blank).
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselLat");
                setVessel((v) => ({ ...v, vesselLat: clamped }));
              }}
              className="w-20 px-1.5 py-0.5"
              style={{ background: THEME.deepNavy, color: THEME.tealSoft, border: `1px solid ${THEME.navyLine}` }}
            />
          </label>
          <label className="flex items-center gap-1.5" style={{ color: THEME.muted }}>
            LON
            <input
              type="number"
              step="0.0001"
              min={-180}
              max={180}
              value={vessel.vesselLon}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselLon");
                setVessel((v) => ({ ...v, vesselLon: clamped }));
              }}
              className="w-20 px-1.5 py-0.5"
              style={{ background: THEME.deepNavy, color: THEME.tealSoft, border: `1px solid ${THEME.navyLine}` }}
            />
          </label>
          <label className="flex items-center gap-1.5" style={{ color: THEME.muted }}>
            HDG
            <input
              type="number"
              step="1"
              min={0}
              max={359}
              value={vessel.vesselHeadingDeg}
              // min/max on a number input are advisory only — the browser
              // still accepts typed values outside that range (e.g. 999),
              // which the backend then rejects with a 400. Clamp here so a
              // bad heading is impossible to submit in the first place.
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselHeadingDeg");
                setVessel((v) => ({ ...v, vesselHeadingDeg: clamped }));
              }}
              className="w-16 px-1.5 py-0.5"
              style={{ background: THEME.deepNavy, color: THEME.tealSoft, border: `1px solid ${THEME.navyLine}` }}
            />
          </label>

          <label
            className="flex items-center gap-1.5 px-3 py-1 cursor-pointer"
            style={{ background: THEME.teal, color: "#04141A", borderRadius: 4, fontWeight: 600 }}
          >
            {isAnalyzing ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            {isAnalyzing ? "ANALYZING…" : file ? "RE-UPLOAD SONAR IMAGE" : "UPLOAD SONAR IMAGE"}
            <input
              type="file"
              accept="image/*,.xtf,.jsf"
              onChange={handleFileUpload}
              hidden
              disabled={isAnalyzing}
            />
          </label>

          <span className="ml-auto" style={{ color: THEME.muted }}>
            {analysis
              ? `${detections.length} targets · vessel ${vessel.vesselLat.toFixed(4)}, ${vessel.vesselLon.toFixed(4)}`
              : "Upload a side-scan sonar image to plot real detections"}
          </span>
        </div>

        {error && (
          <div
            className="px-4 py-2 text-[11px]"
            style={{ background: "#3a1113", color: "#ffb4b4", fontFamily: "var(--font-mono)" }}
          >
            {error} — is the backend running at the configured API base URL?
          </div>
        )}

        {/* Map canvas */}
        <div className="relative" style={{ height: "580px" }}>
          <DetectionMap
            detections={visible}
            vessel={vessel}
            viewMode={viewMode}
            selected={selected}
            onSelect={setSelected}
          />

          {/* Filter panel. Scrolls internally and is capped below the map's own
              height (with room left for the cursor readout) — with 7 real
              classes (up from the original 3) this panel got tall enough to
              overlap whatever sits below it on a short viewport. */}
          <div
            className="absolute left-4 top-4 z-[500] flex flex-col gap-4 p-4"
            style={{
              width: "220px",
              maxHeight: "calc(100% - 32px)",
              overflowY: "auto",
              borderRadius: "14px",
              background: "rgba(15,44,59,0.82)",
              backdropFilter: "blur(8px)",
              WebkitBackdropFilter: "blur(8px)",
              border: `1px solid ${THEME.navyLine}`,
            }}
          >
            <div className="text-sm font-semibold" style={{ color: "#EAF6F4", fontFamily: "var(--font-display)" }}>
              Filter detections
            </div>

            <div>
              <div className="flex justify-between mb-1.5">
                <span className="text-[11px]" style={{ color: "#B7CBCF" }}>Confidence ≥</span>
                <span
                  className="text-[11px] font-semibold"
                  style={{ color: THEME.tealSoft, fontFamily: "var(--font-mono)" }}
                >
                  {threshold}%
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full h-1.5"
                style={{ accentColor: THEME.teal }}
              />
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide mb-2" style={{ color: THEME.muted }}>Class</div>
              {KNOWN_CLASSES.map((cls) => (
                <label key={cls} className="flex items-center gap-2 mb-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={activeClasses.has(cls)}
                    onChange={() => toggle(cls)}
                    style={{ accentColor: THEME.teal }}
                  />
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: classColor(cls) }} />
                  <span className="text-[11px]" style={{ color: "#D6E7E5" }}>{CLASS_META[cls].label}</span>
                </label>
              ))}
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: THEME.muted }}>View</div>
              <div className="flex rounded overflow-hidden" style={{ border: `1px solid ${THEME.navyLine}` }}>
                {(["pins", "heatmap"] as const).map((m) => (
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

            <div
              className="pt-2 text-[9px]"
              style={{ borderTop: `1px solid ${THEME.navyLine}`, color: THEME.muted }}
            >
              {visible.length} / {detections.length} shown
            </div>
          </div>

          {/* Selection popup — real fields from the backend target. */}
          {selDet && (
            <div
              className="absolute z-[500] p-4"
              style={{
                width: "244px",
                right: "16px",
                top: "16px",
                borderRadius: "14px",
                background: "rgba(15,44,59,0.94)",
                backdropFilter: "blur(8px)",
                WebkitBackdropFilter: "blur(8px)",
                border: `1px solid ${THEME.navyLine}`,
                boxShadow: "0 12px 32px rgba(0,0,0,0.4)",
              }}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <div
                    className="text-sm font-semibold"
                    style={{ color: "#EAF6F4", fontFamily: "var(--font-display)" }}
                  >
                    {selDet.label}
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
                  { l: "Risk tier", v: selDet.riskTier },
                  { l: "Latitude", v: selDet.lat.toFixed(5) + "°" },
                  { l: "Longitude", v: selDet.lon.toFixed(5) + "°" },
                  { l: "Length", v: selDet.lengthM ? selDet.lengthM.toFixed(1) + " m" : "n/a" },
                  { l: "Height", v: selDet.heightM ? selDet.heightM.toFixed(1) + " m" : "n/a" },
                ].map((row) => (
                  <div key={row.l} className="flex justify-between items-center">
                    <span className="text-[10px]" style={{ color: THEME.muted }}>{row.l}</span>
                    {row.accent ? (
                      <span
                        className="text-[10px] font-semibold px-2 py-0.5"
                        style={{
                          background: classColor(selDet.cls),
                          color: "#04141A",
                          borderRadius: "4px",
                          fontFamily: "var(--font-mono)",
                        }}
                      >
                        {row.v}
                      </span>
                    ) : (
                      <span
                        className="text-[10px]"
                        style={{ color: "#D6E7E5", fontFamily: "var(--font-mono)" }}
                      >
                        {row.v}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No separate "Class legend" panel — the Filter panel above already
              lists every class with its colour swatch, and with 7 real
              classes (up from 3) a second copy of the same list just
              overlapped it on shorter viewports. The "N / M shown" count
              lives in the Filter panel's own footer now. */}

          {/* Bathymetry (depth) legend — the real GEBCO colour ramp and depth
              values, fetched live from INCOIS's own GetLegendGraphic endpoint
              (JSON form) and rendered as our own dark-theme gradient bar, so
              the numbers sit on a dark background with real contrast instead
              of INCOIS's raw PNG (white background, tiny baked-in black text
              — illegible dropped onto a dark panel). */}
          {depthStops && depthStops.length > 0 && (
            <div
              className="absolute bottom-16 right-3 z-[500] p-3 flex items-center gap-3"
              style={{
                borderRadius: "10px",
                background: "rgba(15,44,59,0.92)",
                backdropFilter: "blur(8px)",
                WebkitBackdropFilter: "blur(8px)",
                border: `1px solid ${THEME.navyLine}`,
              }}
            >
              <div className="flex items-center gap-2">
                <div
                  style={{
                    width: "14px",
                    height: "84px",
                    borderRadius: "3px",
                    border: `1px solid ${THEME.navyLine}`,
                    background: `linear-gradient(to top, ${[...depthStops]
                      .sort((a, b) => a.quantity - b.quantity)
                      .map((s) => s.color)
                      .join(", ")})`,
                  }}
                />
                <div className="flex flex-col justify-between" style={{ height: "84px" }}>
                  <span
                    className="text-[10px] font-semibold"
                    style={{ color: "#EAF6F4", fontFamily: "var(--font-mono)" }}
                  >
                    {Math.max(...depthStops.map((s) => s.quantity))} m
                  </span>
                  <span
                    className="text-[10px] font-semibold"
                    style={{ color: "#EAF6F4", fontFamily: "var(--font-mono)" }}
                  >
                    {Math.min(...depthStops.map((s) => s.quantity))} m
                  </span>
                </div>
              </div>
              <span
                className="text-[11px] leading-snug font-semibold"
                style={{ color: THEME.tealSoft, maxWidth: "64px" }}
              >
                Seafloor depth (INCOIS)
              </span>
            </div>
          )}

          {/* Export button — real CSV report from the backend. */}
          <div className="absolute top-4 right-4 z-[500]">
            <button
              onClick={handleExport}
              disabled={!analysis || isExporting}
              className="flex items-center gap-2 text-sm px-4 py-2.5 font-semibold transition-colors"
              style={{
                background: analysis ? THEME.teal : THEME.navyLine,
                color: analysis ? "#04141A" : THEME.muted,
                borderRadius: "4px",
                cursor: analysis && !isExporting ? "pointer" : "not-allowed",
              }}
            >
              <Download size={14} />
              {isExporting ? "Exporting…" : "Export detections (CSV)"}
            </button>
          </div>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════
          SECTION 2 — REAL ANNOTATED OUTPUT
          Shows the actual prediction image the backend drew
          (bounding boxes + shadow arrows). Only appears once a
          real analysis exists — no placeholder claims.
      ══════════════════════════════════════════════════ */}
      {predictionImageUrl && (
        <section
          className="page-shell"
          style={{ background: THEME.lightBg, padding: "48px 24px" }}
          aria-labelledby="annotated-title"
        >
          <div className="mb-6">
            <p className="eyebrow flex items-center gap-2" style={{ color: THEME.teal }}>
              <span style={{ width: "18px", height: "2px", background: THEME.teal, display: "inline-block" }} />
              DETECTION OUTPUT
            </p>
            <h2
              id="annotated-title"
              style={{ color: THEME.ink, fontFamily: "var(--font-display)", fontWeight: 800, fontSize: "26px", margin: "6px 0" }}
            >
              ANNOTATED <span style={{ color: THEME.teal }}>SONAR FRAME</span>
            </h2>
            <p style={{ color: THEME.muted, maxWidth: "560px", fontSize: "14px" }}>
              The uploaded frame with the model's bounding boxes and acoustic-shadow markers drawn on it —
              the exact source for every point plotted on the map above.
            </p>
          </div>
          <div
            className="relative w-full overflow-hidden"
            style={{
              borderRadius: "12px",
              border: `1px solid ${THEME.border}`,
              boxShadow: "0 4px 16px rgba(10,37,64,0.06)",
              background: "#050D12",
            }}
          >
            <img src={predictionImageUrl} alt="Annotated sonar detection output" className="w-full h-auto" />
          </div>
        </section>
      )}

      {/* ══════════════════════════════════════════════════
          SECTION 3 — DETECTION SUMMARY TABLE (real data)
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
              How many targets of each class were flagged this survey, with average and peak model
              confidence per class. Populated from the real analysis — upload a frame to fill it.
            </p>
          </div>
          <div
            className="flex items-center gap-3 px-4 py-2.5"
            style={{ background: THEME.lightBg, border: `1px solid ${THEME.border}`, borderRadius: "8px" }}
          >
            <span className="text-[11px]" style={{ color: THEME.muted }}>Total detections</span>
            <span className="text-lg font-bold" style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}>
              {detections.length}
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
                {["Class", "Count", "Share of total", "Avg. confidence", "Peak confidence"].map((h) => (
                  <th
                    key={h}
                    className="text-left px-5 py-3"
                    style={{
                      color: "#EAF6F4",
                      fontSize: "10px",
                      letterSpacing: "0.06em",
                      textTransform: "uppercase",
                      fontFamily: "var(--font-mono)",
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
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: classColor(row.cls) }} />
                      <span className="text-[13px] font-semibold" style={{ color: THEME.ink }}>
                        {CLASS_META[row.cls].label}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className="text-[13px] font-semibold"
                      style={{ color: THEME.ink, fontFamily: "var(--font-mono)" }}
                    >
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
                          style={{ width: `${row.share}%`, background: classColor(row.cls) }}
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
                        background: `${classColor(row.cls)}1A`,
                        color: classColor(row.cls),
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
                  {detections.length}
                </td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted }}>
                  {detections.length ? "100%" : "0%"}
                </td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                  {totalAvg}% avg
                </td>
                <td className="px-5 py-3 text-[12px]" style={{ color: THEME.muted, fontFamily: "var(--font-mono)" }}>
                  {totalMax}% max
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>
  );
}
