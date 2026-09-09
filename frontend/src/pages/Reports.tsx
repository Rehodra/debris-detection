import { useState, useMemo } from "react";
import { FileJson, FileSpreadsheet, Download, Search, CheckCircle2, AlertTriangle, Filter } from "lucide-react";

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

const HEADERS = ["Detection ID", "Class", "Confidence", "Lat / Lon", "Depth", "Track", "Timestamp", "Status"];

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
  const [fmt, setFmt] = useState<"json" | "csv">("json");
  const [open, setOpen] = useState(true);
  const [statusFilter, setStatusFilter] = useState<"all" | "Confirmed" | "Needs Review">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filteredItems = useMemo(() => {
    return ALL.filter((d) => {
      const matchStatus = statusFilter === "all" || d.status === statusFilter;
      const matchSearch =
        searchQuery.trim() === "" ||
        d.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.cls.toLowerCase().includes(searchQuery.toLowerCase()) ||
        d.track.toLowerCase().includes(searchQuery.toLowerCase());
      return matchStatus && matchSearch;
    });
  }, [statusFilter, searchQuery]);

  // Synchronized Dynamic Export: JSON and CSV always contain the EXACT SAME targets with identical item count
  const jsonContent = useMemo(() => {
    return JSON.stringify(
      {
        export_metadata: {
          generated_at: new Date().toISOString(),
          survey_vessel: "RV-Explorer",
          vehicle_id: "AUV-PALKBAY-02",
          mission_id: "S-2023-11A",
          target_count: filteredItems.length,
          confirmed_count: filteredItems.filter((d) => d.status === "Confirmed").length,
          review_count: filteredItems.filter((d) => d.status === "Needs Review").length,
        },
        detections: filteredItems.map((d) => ({
          detection_id: d.id,
          class_name: d.cls,
          confidence: d.conf / 100,
          coordinates: {
            latitude: parseFloat(d.lat.replace("°N", "")),
            longitude: parseFloat(d.lon.replace("°E", "")),
          },
          water_depth_m: parseInt(d.depth.replace(" m", ""), 10),
          track_id: d.track,
          timestamp: d.ts,
          verification_status: d.status.toLowerCase().replace(" ", "_"),
        })),
      },
      null,
      2
    );
  }, [filteredItems]);

  const csvContent = useMemo(() => {
    const csvHeaders = [
      "detection_id",
      "class_name",
      "confidence",
      "latitude",
      "longitude",
      "water_depth_m",
      "track_id",
      "timestamp",
      "verification_status",
    ];
    const rows = filteredItems.map((d) =>
      [
        d.id,
        `"${d.cls}"`,
        (d.conf / 100).toFixed(2),
        d.lat.replace("°N", ""),
        d.lon.replace("°E", ""),
        d.depth.replace(" m", ""),
        d.track,
        `"${d.ts}"`,
        d.status.toLowerCase().replace(" ", "_"),
      ].join(",")
    );
    return [csvHeaders.join(","), ...rows].join("\r\n");
  }, [filteredItems]);

  const handleExport = (format: "json" | "csv") => {
    setFmt(format);
    const dateStr = new Date().toISOString().slice(0, 10);
    const filename = `marinescan_detections_${dateStr}.${format}`;
    const content = format === "json" ? jsonContent : csvContent;
    const mime = format === "json" ? "application/json" : "text/csv;charset=utf-8;";

    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const confirmed = ALL.filter((d) => d.status === "Confirmed").length;
  const needsReview = ALL.filter((d) => d.status === "Needs Review").length;

  return (
    <div className="reports-page page-enter" style={{ fontFamily: "var(--font-body)" }}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
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

          {/* Symmetrical Equal-Size Export Buttons */}
          <div className="reports-export-actions flex items-center gap-3 w-full sm:w-auto">
            <button
              onClick={() => handleExport("json")}
              className="flex-1 sm:flex-initial min-w-[150px] h-[38px] bg-[#0E4749] hover:bg-[#135f62] text-white text-xs px-4 font-semibold transition-all flex items-center justify-center gap-2 shadow-sm"
              style={{ borderRadius: "6px" }}
              title="Export synchronized detection records as JSON"
            >
              <FileJson className="w-4 h-4 text-[#8fe2d9]" />
              <span>Export JSON ({filteredItems.length})</span>
            </button>
            <button
              onClick={() => handleExport("csv")}
              className="flex-1 sm:flex-initial min-w-[150px] h-[38px] bg-[#1C7C72] hover:bg-[#23998d] text-white text-xs px-4 font-semibold transition-all flex items-center justify-center gap-2 shadow-sm"
              style={{ borderRadius: "6px" }}
              title="Export synchronized detection records as CSV"
            >
              <FileSpreadsheet className="w-4 h-4 text-[#a8f3ea]" />
              <span>Export CSV ({filteredItems.length})</span>
            </button>
          </div>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 bg-white p-3 rounded-lg border border-[#E4F1EE]">
          <div className="flex items-center gap-2">
            <Filter className="w-3.5 h-3.5 text-[#7C9490]" />
            <span className="text-[11px] font-semibold text-[#0E4749]">Filter:</span>
            <div className="flex gap-1.5">
              {(
                [
                  { id: "all", label: `All (${ALL.length})` },
                  { id: "Confirmed", label: `Confirmed (${confirmed})` },
                  { id: "Needs Review", label: `Needs Review (${needsReview})` },
                ] as const
              ).map((chip) => (
                <button
                  key={chip.id}
                  onClick={() => setStatusFilter(chip.id)}
                  className={`text-[10.5px] px-2.5 py-1 rounded transition-colors font-medium ${
                    statusFilter === chip.id
                      ? "bg-[#0E4749] text-white"
                      : "bg-[#F3FAF8] text-[#7C9490] hover:bg-[#E4F1EE]"
                  }`}
                >
                  {chip.label}
                </button>
              ))}
            </div>
          </div>

          <div className="relative flex items-center min-w-[200px]">
            <Search className="w-3.5 h-3.5 text-[#7C9490] absolute left-2.5" />
            <input
              type="text"
              placeholder="Search ID, class, track..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1 text-xs border border-[#E4F1EE] rounded bg-[#F9FCFB] focus:outline-none focus:border-[#1C7C72]"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-5">
          {/* Table */}
          <div className="bg-white border border-[#E4F1EE] overflow-hidden" style={{ borderRadius: "14px" }}>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="bg-[#F3FAF8] border-b border-[#E4F1EE]">
                    {HEADERS.map((h) => (
                      <th
                        key={h}
                        className="text-left px-4 py-3 text-[#7C9490] font-medium whitespace-nowrap text-[10px] uppercase tracking-wide"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((d) => {
                    const isSelected = selectedId === d.id;
                    return (
                      <tr
                        key={d.id}
                        onClick={() => setSelectedId(d.id)}
                        className={`border-b border-[#E4F1EE] hover:bg-[#F3FAF8] transition-colors cursor-pointer ${
                          isSelected ? "bg-[#EAF5F2]" : ""
                        }`}
                        style={
                          d.status === "Needs Review"
                            ? { borderLeft: "3px solid #F2A94E" }
                            : { borderLeft: "3px solid transparent" }
                        }
                      >
                        <td className="px-4 py-2.5 text-[#132A2E] font-medium" style={{ fontFamily: "var(--font-mono)" }}>
                          {d.id}
                        </td>
                        <td className="px-4 py-2.5 text-[#132A2E] font-semibold whitespace-nowrap">{d.cls}</td>
                        <td className="px-4 py-2.5">
                          <ConfChip v={d.conf} />
                        </td>
                        <td className="px-4 py-2.5 text-[#132A2E] whitespace-nowrap" style={{ fontFamily: "var(--font-mono)" }}>
                          {d.lat}
                          <br />
                          <span className="text-[#7C9490]">{d.lon}</span>
                        </td>
                        <td className="px-4 py-2.5 text-[#132A2E]" style={{ fontFamily: "var(--font-mono)" }}>
                          {d.depth}
                        </td>
                        <td className="px-4 py-2.5 text-[#132A2E]" style={{ fontFamily: "var(--font-mono)" }}>
                          {d.track}
                        </td>
                        <td className="px-4 py-2.5 text-[#7C9490] whitespace-nowrap" style={{ fontFamily: "var(--font-mono)" }}>
                          {d.ts}
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className="text-[10px] px-2 py-0.5"
                            style={{
                              borderRadius: "4px",
                              background: d.status === "Confirmed" ? "#E4F1EE" : "transparent",
                              color: d.status === "Confirmed" ? "#1C7C72" : "#F2A94E",
                              border: d.status !== "Confirmed" ? "1px solid #F2A94E" : "none",
                              fontWeight: 600,
                            }}
                          >
                            {d.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                  {filteredItems.length === 0 && (
                    <tr>
                      <td colSpan={HEADERS.length} className="text-center py-8 text-[#7C9490]">
                        No detections match the search and filter criteria.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Synchronized Live Preview Pane */}
          <div className="bg-white border border-[#E4F1EE] flex flex-col overflow-hidden" style={{ borderRadius: "14px" }}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#E4F1EE] shrink-0">
              <div>
                <div className="text-sm font-semibold text-[#0E4749]" style={{ fontFamily: "var(--font-display)" }}>
                  Synchronized export preview
                </div>
                <div className="text-[10px] text-[#7C9490]">
                  {filteredItems.length} items ready for 1:1 export
                </div>
              </div>
              <div className="reports-preview-controls flex items-center gap-3">
                <div className="reports-format-toggle flex rounded overflow-hidden border border-[#E4F1EE]">
                  {(["json", "csv"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFmt(f)}
                      className={`text-[10px] px-3 py-1 uppercase font-semibold tracking-wide transition-colors ${
                        fmt === f ? "bg-[#0E4749] text-[#F3FAF8]" : "text-[#7C9490] hover:bg-[#E4F1EE]"
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <button className="reports-collapse text-[10px] text-[#7C9490] hover:text-[#132A2E]" onClick={() => setOpen(!open)}>
                  {open ? "collapse" : "expand"}
                </button>
              </div>
            </div>

            {open && (
              <div className="flex-1 overflow-auto bg-[#E4F1EE] p-4 min-h-0 max-h-[480px]">
                <pre
                  className="reports-code text-[11px] text-[#132A2E] leading-relaxed whitespace-pre-wrap break-words"
                  style={{ fontFamily: "var(--font-mono)" }}
                >
                  {fmt === "json" ? jsonContent : csvContent}
                </pre>
              </div>
            )}

            <div className="px-4 py-3 border-t border-[#E4F1EE] shrink-0 bg-[#F9FCFB] flex items-center justify-between">
              <p className="text-[9.5px] text-[#7C9490] leading-relaxed">
                JSON and CSV exports are strictly synchronized to contain the exact same target count.
              </p>
              <button
                onClick={() => handleExport(fmt)}
                className="text-[10.5px] text-[#0E4749] hover:text-[#135f62] font-semibold flex items-center gap-1"
              >
                <Download className="w-3 h-3" />
                <span>Download {fmt.toUpperCase()}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

