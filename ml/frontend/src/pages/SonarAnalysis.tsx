import React, { useState, useEffect, ChangeEvent } from 'react';
import {
  Upload, Download, RefreshCw, ScanLine,
  ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, Layers,
  CheckCircle2, Circle, FileJson
} from 'lucide-react';
import styles from './SonarAnalysis.module.scss';
import { AnalysisTarget, MasterAnalysisResult, VesselParams, analyzeSonarImage, downloadAnalysisReport } from '../api/client';
import { SurveyMap, SensorPosition } from '../components/SurveyMap';

const API_BASE = 'http://127.0.0.1:8000';

// A point well out in the Bay of Bengal off the Chennai coast (the coastline itself
// sits around lon 80.28-80.30 — anything near that longitude lands on the city, not water).
const DEFAULT_VESSEL_LAT = 13.05;
const DEFAULT_VESSEL_LON = 80.42;
const DEFAULT_VESSEL_HEADING = 90;

export const SonarAnalysis: React.FC = () => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<MasterAnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [vesselLat, setVesselLat] = useState<number>(DEFAULT_VESSEL_LAT);
  const [vesselLon, setVesselLon] = useState<number>(DEFAULT_VESSEL_LON);
  const [vesselHeading, setVesselHeading] = useState<number>(DEFAULT_VESSEL_HEADING);
  const [backendReachable, setBackendReachable] = useState<boolean | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/health`)
      .then((r) => setBackendReachable(r.ok))
      .catch(() => setBackendReachable(false));
  }, []);

  const vesselParams: VesselParams = { vesselLat, vesselLon, vesselHeadingDeg: vesselHeading };

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    setImageSrc(url);
    setSelectedFile(file);
    setAnalysis(null);
    setError(null);
    setIsAnalyzing(true);

    analyzeSonarImage(file, vesselParams)
      .then(setAnalysis)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsAnalyzing(false));
  };

  const analysisDone = analysis !== null;
  const targets = analysis?.targets ?? [];
  const displayImage = analysis?.prediction_image_url || imageSrc;
  const sensorPosition: SensorPosition | null = analysisDone ? { latitude: vesselLat, longitude: vesselLon } : null;

  const handleExport = async (format: 'json' | 'csv') => {
    if (!selectedFile) return;
    setIsExporting(true);
    try {
      await downloadAnalysisReport(selectedFile, format, vesselParams);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const formatTargetType = (target: AnalysisTarget) => target.class_name.replace('_', ' ').toUpperCase();

  const showSidePanel = imageSrc !== null;

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          <span>MISSION <strong>{analysis?.mission_id ?? '—'}</strong></span>
        </div>
        <div className={styles.statusBadges}>
          {backendReachable === null ? (
            <span className={styles.statusDot}><i className={styles.dotAmber}></i> CHECKING BACKEND…</span>
          ) : backendReachable ? (
            <span className={styles.statusDot}><i className={styles.dotGreen}></i> BACKEND REACHABLE</span>
          ) : (
            <span className={styles.badgeDanger}>BACKEND UNREACHABLE</span>
          )}
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
                <button className={styles.iconBtn}><ZoomIn size={14} /></button>
                <button className={styles.iconBtn}><ZoomOut size={14} /></button>
                <button className={styles.iconBtn}><Maximize size={14} /></button>
                <button className={styles.layerToggle}><Layers size={13} /> ON</button>
              </div>
            </div>

            {!imageSrc && (
              <div style={{ display: 'flex', gap: 12, padding: '10px 16px 0', fontSize: 12, color: '#6b7490' }}>
                <label>
                  Vessel Lat{' '}
                  <input type="number" step="0.0001" value={vesselLat} onChange={(e) => setVesselLat(parseFloat(e.target.value))} style={{ width: 90 }} />
                </label>
                <label>
                  Vessel Lon{' '}
                  <input type="number" step="0.0001" value={vesselLon} onChange={(e) => setVesselLon(parseFloat(e.target.value))} style={{ width: 90 }} />
                </label>
                <label>
                  Heading (°){' '}
                  <input type="number" step="1" value={vesselHeading} onChange={(e) => setVesselHeading(parseFloat(e.target.value))} style={{ width: 70 }} />
                </label>
              </div>
            )}

            <div className={styles.imageCanvas}>
              {!imageSrc ? (
                <label htmlFor="sonar-upload" className={styles.uploadDropzone}>
                  <div className={styles.uploadIconWrap}>
                    <Upload size={28} />
                  </div>
                  <h3>Upload Sonar Image</h3>
                  <p>Click or drag a side-scan sonar image file to begin analysis</p>
                  <input type="file" id="sonar-upload" accept="image/*" onChange={handleFileUpload} hidden />
                </label>
              ) : (
                <div className={styles.sonarViewport}>
                  <img src={displayImage ?? imageSrc} alt="Sonar Scan" className={styles.sonarImage} />

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
                      <span>VESSEL LAT <strong>{vesselLat.toFixed(4)}</strong></span>
                      <span>VESSEL LON <strong>{vesselLon.toFixed(4)}</strong></span>
                      <span>HDG <strong>{vesselHeading}°</strong></span>
                      <span>QUALITY <strong>{analysis?.quality_assessment.quality_tier ?? '—'}</strong></span>
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
                {['INPUT', 'PREPROCESS', 'YOLO', 'SHADOW', 'PHYSICS', 'CONFIDENCE'].map((step) => (
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
                  {error ? (
                    <div className={styles.detectionCardAlert}><div className={styles.cardMain}><span className={styles.targetTitle}>{error}</span></div></div>
                  ) : !analysisDone ? (
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
                  <div className={styles.panelBlockHeader}>
                    <span>SURVEY MAP</span>
                    <span className={styles.countBadge}>{analysis.geojson.features.length} pinned</span>
                  </div>
                  <div className={styles.panelBlockBody}>
                    <SurveyMap geojson={analysis.geojson as any} sensorPosition={sensorPosition} />
                  </div>
                </div>
              )}

              {analysisDone && targets.length > 0 && (
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
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SonarAnalysis;
