import { useState } from "react";

const ALL = [
  { id:"DET-001", cls:"Entangled Net", conf:91, lat:"10.4823°N", lon:"72.6341°E", depth:"28 m", track:"TRK-042", ts:"2026-09-05 14:32", status:"Confirmed" },
  { id:"DET-002", cls:"Steel Pipe",    conf:76, lat:"10.4819°N", lon:"72.6338°E", depth:"29 m", track:"TRK-042", ts:"2026-09-05 14:35", status:"Confirmed" },
  { id:"DET-003", cls:"Cylinder",      conf:61, lat:"10.4815°N", lon:"72.6330°E", depth:"31 m", track:"TRK-042", ts:"2026-09-05 14:37", status:"Needs Review" },
  { id:"DET-004", cls:"Entangled Net", conf:84, lat:"10.4810°N", lon:"72.6325°E", depth:"27 m", track:"TRK-042", ts:"2026-09-05 14:39", status:"Confirmed" },
  { id:"DET-005", cls:"Shipwreck",     conf:95, lat:"10.4806°N", lon:"72.6318°E", depth:"34 m", track:"TRK-042", ts:"2026-09-05 14:42", status:"Confirmed" },
  { id:"DET-006", cls:"Cylinder",      conf:72, lat:"10.4802°N", lon:"72.6312°E", depth:"36 m", track:"TRK-042", ts:"2026-09-05 14:44", status:"Needs Review" },
  { id:"DET-007", cls:"Entangled Net", conf:88, lat:"10.4798°N", lon:"72.6308°E", depth:"25 m", track:"TRK-041", ts:"2026-09-04 09:11", status:"Confirmed" },
  { id:"DET-008", cls:"Steel Pipe",    conf:79, lat:"10.4793°N", lon:"72.6302°E", depth:"30 m", track:"TRK-041", ts:"2026-09-04 09:14", status:"Confirmed" },
];

const JSON_SNIPPET = `{
  "export": {
    "generated": "2026-09-05T15:00:00Z",
    "vehicle": "AUV-PALKBAY-02",
    "total": 8
  },
  "detections": [
    {
      "id": "DET-001",
      "class": "Entangled Net",
      "confidence": 0.91,
      "lat": 10.4823,
      "lon": 72.6341,
      "depth_m": 28,
      "track_id": "TRK-042",
      "timestamp": "2026-09-05T14:32:00Z",
      "status": "confirmed"
    }
  ]
}`;

const CSV_SNIPPET = `id,class,confidence,lat,lon,depth_m,track_id,timestamp,status
DET-001,Entangled Net,0.91,10.4823,72.6341,28,TRK-042,2026-09-05T14:32:00Z,confirmed
DET-002,Steel Pipe,0.76,10.4819,72.6338,29,TRK-042,2026-09-05T14:35:00Z,confirmed
DET-003,Cylinder,0.61,10.4815,72.6330,31,TRK-042,2026-09-05T14:37:00Z,needs_review`;

const HEADERS = ["Detection ID","Class","Confidence","Lat / Lon","Depth","Track","Timestamp","Status"];

function ConfChip({ v }: { v: number }) {
  const bg   = v >= 90 ? "#E8604C" : v >= 70 ? "#F2A94E" : "transparent";
  const text = v >= 70 ? "white"   : "#7C9490";
  const bdr  = v < 70  ? "1px solid #7C9490" : "none";
  return (
    <span style={{ background: bg, color: text, border: bdr, borderRadius:"4px",
      fontFamily:"var(--font-mono)", fontSize:"10px", fontWeight:600, padding:"2px 6px" }}>
      {v}%
    </span>
  );
}

export default function Reports() {
  const [fmt, setFmt] = useState<"json"|"csv">("json");
  const [open, setOpen] = useState(true);

  const confirmed   = ALL.filter(d => d.status === "Confirmed").length;
  const needsReview = ALL.filter(d => d.status === "Needs Review").length;

  return (
    <div className="reports-page page-enter" style={{ fontFamily: "var(--font-body)" }}>
      <div className="max-w-7xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="flex items-start justify-between mb-7 flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-[#0E4749] mb-1" style={{ fontFamily: "var(--font-display)" }}>
              Detection Reports
            </h1>
            <div className="flex gap-4 text-[11px]">
              <span className="text-[#7C9490]">{ALL.length} total detections</span>
              <span className="text-[#1C7C72] font-medium">{confirmed} confirmed</span>
              <span className="text-[#F2A94E] font-medium">{needsReview} needs review</span>
            </div>
          </div>

          <div className="reports-export-actions flex gap-3">
            {[
              { lbl: "Export as CSV",  act: () => setFmt("csv") },
              { lbl: "Export as JSON", act: () => setFmt("json") },
            ].map(b => (
              <button
                key={b.lbl}
                onClick={b.act}
                className="border border-[#0E4749] text-[#0E4749] text-xs px-4 py-2 font-semibold hover:bg-[#E4F1EE] transition-colors flex items-center gap-1.5"
                style={{ borderRadius: "4px" }}
              >
                <svg viewBox="0 0 14 14" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                  <path d="M3 12h8M7 2v7M4.5 7L7 9.5 9.5 7"/>
                </svg>
                {b.lbl}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-5">

          {/* Table */}
          <div className="bg-white border border-[#E4F1EE] overflow-hidden" style={{ borderRadius: "14px" }}>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="bg-[#F3FAF8] border-b border-[#E4F1EE]">
                    {HEADERS.map(h=>(
                      <th key={h} className="text-left px-4 py-3 text-[#7C9490] font-medium whitespace-nowrap text-[10px] uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ALL.map(d=>(
                    <tr
                      key={d.id}
                      className="border-b border-[#E4F1EE] hover:bg-[#F3FAF8] transition-colors"
                      style={d.status==="Needs Review"
                        ? { borderLeft: "3px solid #F2A94E" }
                        : { borderLeft: "3px solid transparent" }
                      }
                    >
                      <td className="px-4 py-2.5 text-[#132A2E] font-medium" style={{fontFamily:"var(--font-mono)"}}>{d.id}</td>
                      <td className="px-4 py-2.5 text-[#132A2E] font-semibold whitespace-nowrap">{d.cls}</td>
                      <td className="px-4 py-2.5"><ConfChip v={d.conf}/></td>
                      <td className="px-4 py-2.5 text-[#132A2E] whitespace-nowrap" style={{fontFamily:"var(--font-mono)"}}>
                        {d.lat}<br/><span className="text-[#7C9490]">{d.lon}</span>
                      </td>
                      <td className="px-4 py-2.5 text-[#132A2E]" style={{fontFamily:"var(--font-mono)"}}>{d.depth}</td>
                      <td className="px-4 py-2.5 text-[#132A2E]" style={{fontFamily:"var(--font-mono)"}}>{d.track}</td>
                      <td className="px-4 py-2.5 text-[#7C9490] whitespace-nowrap" style={{fontFamily:"var(--font-mono)"}}>{d.ts}</td>
                      <td className="px-4 py-2.5">
                        <span
                          className="text-[10px] px-2 py-0.5"
                          style={{
                            borderRadius: "4px",
                            background: d.status==="Confirmed" ? "#E4F1EE" : "transparent",
                            color: d.status==="Confirmed" ? "#1C7C72" : "#F2A94E",
                            border: d.status!=="Confirmed" ? "1px solid #F2A94E" : "none",
                            fontWeight: 600,
                          }}
                        >
                          {d.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Preview pane */}
          <div className="bg-white border border-[#E4F1EE] flex flex-col overflow-hidden" style={{ borderRadius: "14px" }}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E4F1EE] shrink-0">
              <div className="text-sm font-semibold text-[#0E4749]" style={{ fontFamily: "var(--font-display)" }}>
                Export preview
              </div>
              <div className="reports-preview-controls flex items-center gap-3">
                <div className="reports-format-toggle flex rounded overflow-hidden border border-[#E4F1EE]">
                  {(["json","csv"] as const).map(f=>(
                    <button key={f} onClick={()=>setFmt(f)}
                      className={`text-[10px] px-3 py-1 uppercase font-semibold tracking-wide transition-colors ${
                        fmt===f ? "bg-[#0E4749] text-[#F3FAF8]" : "text-[#7C9490] hover:bg-[#E4F1EE]"
                      }`}>{f}</button>
                  ))}
                </div>
                <button className="reports-collapse text-[10px] text-[#7C9490] hover:text-[#132A2E]" onClick={()=>setOpen(!open)}>
                  {open?"collapse":"expand"}
                </button>
              </div>
            </div>

            {open && (
              <div className="flex-1 overflow-auto bg-[#E4F1EE] p-4 min-h-0">
                <pre className="reports-code text-[11px] text-[#132A2E] leading-relaxed whitespace-pre-wrap break-words"
                  style={{ fontFamily: "var(--font-mono)" }}>
                  {fmt==="json" ? JSON_SNIPPET : CSV_SNIPPET}
                </pre>
              </div>
            )}

            <div className="px-4 py-3 border-t border-[#E4F1EE] shrink-0">
              <p className="text-[9.5px] text-[#7C9490] leading-relaxed">
                All confirmed detections export by default. Items marked "Needs Review" are included with their status flag — the receiving system decides how to handle them.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
