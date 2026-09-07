import React, { useState, ChangeEvent } from 'react';
import {
  Upload, Download, Radio, MapPin, RefreshCw, ScanLine,
  ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, Layers,
  CheckCircle2, Circle, FileJson
} from 'lucide-react';
import styles from './SonarAnalysis.module.scss';
import { AnalysisTarget, MasterAnalysisResult, analyzeSonarImage, downloadAnalysisReport, resolveApiAssetUrl } from '../api/client';

export const SonarAnalysis: React.FC = () => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<MasterAnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [zoom, setZoom] = useState(1);

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    setImageSrc(url);
    setSelectedFile(file);
    setAnalysis(null);
    setError(null);
    setZoom(1);
    setIsAnalyzing(true);

    analyzeSonarImage(file)
      .then(setAnalysis)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsAnalyzing(false));
  };

  const analysisDone = analysis !== null;
  const targets = analysis?.targets ?? [];
  const displayImage = resolveApiAssetUrl(analysis?.prediction_image_url) || analysis?.annotated_image_base64 || imageSrc;

  const handleExport = async (format: 'json' | 'csv') => {
    if (!selectedFile) return;
    setIsExporting(true);
    try {
      await downloadAnalysisReport(selectedFile, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const formatTargetType = (target: AnalysisTarget) => target.class_name.replace('_', ' ').toUpperCase();

  const showSidePanel = imageSrc !== null;

  return (
    <div className={`${styles.container} sonar-page page-enter`}>
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          <span>VESSEL <strong>RV-Explorer</strong></span>
          <span className={styles.divider}>|</span>
          <span>SURVEY <strong>S-2023-11A</strong></span>
        </div>
        <div className={styles.statusBadges}>
          <span className={styles.statusDot}><i className={styles.dotGreen}></i> SONAR ONLINE</span>
          <span className={styles.statusDot}><i className={styles.dotGreen}></i> GPS FIX</span>
          <span className={styles.badgeDanger}>EDGE MODE</span>
        </div>
      </header>

      <div className={styles.scrollArea}>
        <div className={`${styles.mainContent} ${!showSidePanel ? styles.centered : ''}`}>
          <div className={styles.viewerPanel}>
            <div className={styles.viewerHeader}>
              <span>SONAR VIEWER</span>
              <div className={styles.viewerControls}>
                <button className={styles.iconBtn}><ChevronLeft size={14} /></button>
                <button className={styles.iconBtn}><ChevronRight size={14} /></button>
                <button className={styles.iconBtn} onClick={() => setZoom((value) => Math.min(2.5, Number((value + 0.25).toFixed(2))))} aria-label="Zoom in"><ZoomIn size={14} /></button>
                <button className={styles.iconBtn} onClick={() => setZoom((value) => Math.max(1, Number((value - 0.25).toFixed(2))))} aria-label="Zoom out"><ZoomOut size={14} /></button>
                <button className={styles.iconBtn}><Maximize size={14} /></button>
                <button className={styles.layerToggle}><Layers size={13} /> ON</button>
              </div>
            </div>

            <div className={styles.imageCanvas}>
              {!imageSrc ? (
                <div className={styles.emptyWorkspace}>
                  <aside className={styles.emptyInputColumn}>
                    <label htmlFor="sonar-upload" className={styles.uploadDropzone}>
                      <div className={styles.uploadIconWrap}><Upload size={24} /></div>
                      <span className={styles.uploadEyebrow}>MISSION INPUT</span>
                      <h3>Upload sonar image</h3>
                      <p>Drop a side-scan frame or browse a mission file.</p>
                      <span className={styles.uploadFormats}>JPG / PNG / XTF / JSF</span>
                      <input type="file" id="sonar-upload" accept="image/*,.xtf,.jsf" onChange={handleFileUpload} hidden />
                    </label>
                    <div className={styles.missionMeta}><span>LOG METADATA</span><b>VESSEL ID</b><strong>AUV-PALKBAY-02</strong><b>TRACK ID</b><strong>TRK-042</strong><b>STATUS</b><strong className={styles.metaReady}>READY FOR INPUT</strong></div>
                  </aside>
                  <div className={styles.previewPanel}>
                    <div className={styles.previewTabs}><span className={styles.activeTab}>MORPHOLOGICAL PREPROCESSING</span><span>ACOUSTIC SHADOW ANALYSIS</span><span>YOLO DETECTION OUTPUT</span></div>
                    <div className={styles.previewImage}><img src="/new.png" alt="AquaTrace sonar upload preview" /><span>UPLOAD PREVIEW / RAW SONAR FIELD</span><i>drag to compare</i></div>
                    <div className={styles.previewNote}><strong>WHY THIS STEP MATTERS</strong><p>Raw sonar is noisy. AquaTrace removes speckle, preserves object outlines, and prepares the frame for detection and acoustic validation.</p></div>
                  </div>
                  <aside className={styles.emptyDetections}><div className={styles.emptyDetections__header}><strong>DETECTIONS</strong><span>TRK-042 · 5 found</span></div>{['Entangled Net', 'Steel Pipe', 'Cylinder', 'Entangled Net', 'Shipwreck'].map((name, index) => <div className={styles.emptyDetection} key={`${name}-${index}`}><i /><span><b>{name}</b><small>10.4823°N · {28 + index} m</small></span><strong>{[91, 76, 61, 84, 95][index]}%</strong></div>)}</aside>
                </div>
              ) : (
                <div className={styles.sonarViewport}>
                  <img src={displayImage ?? imageSrc} alt="Sonar Scan" className={styles.sonarImage} style={{ transform: `scale(${zoom})` }} />

                  {isAnalyzing && (
                    <div className={styles.scannerOverlay}>
                      <div className={styles.scanLine}></div>
                      <div className={styles.scanLabel}>
                        <ScanLine size={14} /> ANALYZING ACOUSTIC DATA…
                      </div>
                    </div>
                  )}

                  <div className={styles.imageMetaFooter}>
                    <div className={styles.metaLeft}>
                      <span>LAT <strong>{targets[0]?.coordinates.latitude.toFixed(5) ?? '—'}</strong></span>
                      <span>LON <strong>{targets[0]?.coordinates.longitude.toFixed(5) ?? '—'}</strong></span>
                      <span>QUALITY <strong>{analysis?.quality_assessment.quality_tier ?? '—'}</strong></span>
                      <span>CONF <strong>{analysis ? `${Math.round((targets[0]?.calibrated_confidence ?? 0) * 100)}%` : '—'}</strong></span>
                    </div>
                    <div className={styles.metaRight}>
                      <div><span>FRM</span><strong>0042</strong></div>
                      <div><span>PNG</span><strong>1284</strong></div>
                    </div>
                    <label htmlFor="reupload-btn" className={styles.changeImgBtn}>
                      <RefreshCw size={12} /> Replace
                    </label>
                    <input type="file" id="reupload-btn" accept="image/*" onChange={handleFileUpload} hidden />
                  </div>
                </div>
              )}
            </div>

            {imageSrc && (
              <div className={styles.pipelineBar}>
                <span className={styles.pipelineLabel}>PIPELINE:</span>
                {['INPUT', 'PREPROCESS', 'YOLO', 'SHADOW', 'ANOMALY'].map((step) => (
                  <span key={step} className={analysisDone ? styles.stepDone : styles.stepPending}>
                    {analysisDone ? <CheckCircle2 size={12} /> : <Circle size={12} />} {step}
                  </span>
                ))}
                <span className={analysisDone ? styles.stepActive : styles.stepPending}>
                  <RefreshCw size={12} /> GEO
                </span>
                <span className={styles.stepMuted}>
                  <FileJson size={12} /> JSON
                </span>
              </div>
            )}
          </div>

          {showSidePanel && (
            <div className={styles.sidePanel}>
              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}>
                  <span>DETECTION LIST</span>
                  {analysisDone && <span className={styles.countBadge}>{targets.length} Targets</span>}
                  {analysisDone && (
                    <>
                      <button className={styles.exportBtn} onClick={() => handleExport('json')} disabled={isExporting}><Download size={12} /> EXPORT JSON</button>
                      <button className={styles.exportBtn} onClick={() => handleExport('csv')} disabled={isExporting}><Download size={12} /> CSV</button>
                    </>
                  )}
                </div>

                <div className={styles.panelBlockBody}>
                  {!analysisDone ? (
                    <>
                      <div className={styles.skeletonRow}></div>
                      <div className={styles.skeletonRow}></div>
                    </>
                  ) : (
                    <>
                      {targets.map((target) => (
                        <div key={target.detection_id} className={target.risk_tier === 'CRITICAL' || target.risk_tier === 'HIGH' ? styles.detectionCardAlert : styles.detectionCardWarn}>
                          <div className={styles.cardMain}>
                            <span className={styles.targetTitle}>{formatTargetType(target)}</span>
                            <span className={target.calibrated_confidence >= 0.8 ? styles.targetConfRed : styles.targetConfAmber}>{Math.round(target.calibrated_confidence * 100)}% CONF</span>
                          </div>
                          <div className={styles.cardSub}>
                            <span>{target.risk_tier}</span>
                            <span className={target.trust_tier === 'VERIFIED_TARGET' ? styles.statusVerified : styles.statusReview}>{target.trust_tier.replace(/_/g, ' ')}</span>
                          </div>
                        </div>
                      ))}
                      {targets.length === 0 && <p>No targets detected in this scan.</p>}
                    </>
                  )}
                </div>
              </div>

              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}><span>ACOUSTIC VALIDATION</span></div>
                <div className={styles.panelBlockBody}>
                  {!analysisDone ? (
                    <div className={styles.skeletonRow}></div>
                  ) : (
                    <>
                      <div className={styles.metricRow}><span>Shadow Length</span><strong>{targets[0]?.shadow_evidence.shadow_length_m?.toFixed(2) ?? '—'}m</strong></div>
                      <div className={styles.metricRow}><span>Est. Height</span><strong>{targets[0]?.shadow_evidence.estimated_height_m?.toFixed(2) ?? '—'}m</strong></div>
                      <div className={styles.metricRow}><span>Shadow Score</span><strong className={styles.greenText}>{targets[0] ? `${Math.round(targets[0].shadow_evidence.shadow_score * 100)}%` : '—'}</strong></div>
                    </>
                  )}
                </div>
              </div>

              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}><span>SURVEY INTEL</span></div>
                <div className={styles.panelBlockBody}>
                  {!analysisDone ? (
                    <div className={styles.skeletonRow}></div>
                  ) : (
                    <div className={styles.grid2x2}>
                      <div><small>MISSION</small><h4>{analysis.mission_id}</h4></div>
                      <div><small>TARGETS</small><h4>{analysis.summary.total_targets_detected}</h4></div>
                      <div><small>VERIFIED</small><h4>{analysis.summary.verified_targets}</h4></div>
                      <div><small>QUALITY</small><h4>{Math.round(analysis.quality_assessment.overall_quality_score * 100)}%</h4></div>
                    </div>
                  )}
                </div>
              </div>

              {analysisDone && (
                <div className={styles.panelBlock}>
                  <div className={styles.panelBlockHeader}><span>TARGET CLASSIFICATION</span></div>
                  <div className={styles.panelBlockBody}>
                    <p className={styles.classificationSubtitle}>
                      {analysis.summary.total_targets_detected} TARGETS DETECTED · {analysis.summary.verified_targets} VERIFIED
                    </p>
                    <table className={styles.miniTable}>
                      <thead>
                        <tr>
                          <th>TARGET</th>
                          <th>TYPE</th>
                          <th>LOCATION</th>
                          <th>CONF.</th>
                          <th>SHADOW</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targets.map((target) => (
                          <tr key={target.detection_id}>
                            <td>{target.display_name}</td>
                            <td>{formatTargetType(target)}</td>
                            <td>{target.coordinates.latitude.toFixed(4)}, {target.coordinates.longitude.toFixed(4)}</td>
                            <td>{Math.round(target.calibrated_confidence * 100)}%</td>
                            <td>{Math.round(target.shadow_evidence.shadow_score * 100)}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {analysisDone && (
                <div className={styles.panelBlock}>
                  <div className={styles.panelBlockHeader}><span>SURVEY MAP</span></div>
                  <div className={styles.panelBlockBody}>
                    <div className={styles.mapMock}>
                      <img src="/surveymap.jpeg" alt="Survey Map" className={styles.mapImage} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SonarAnalysis;