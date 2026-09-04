import React, { useState, ChangeEvent } from 'react';
import {
  Upload, Download, Radio, MapPin, RefreshCw, ScanLine,
  ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, Layers,
  CheckCircle2, Circle, FileJson
} from 'lucide-react';
import styles from './SonarAnalysis.module.scss';

interface Target {
  id: string;
  type: string;
  location: string;
  conf: string;
  shadow: string;
}

const MOCK_TARGETS: Target[] = [
  { id: 'Ghost Net', type: 'Entanglement', location: '15.498, 73.827', conf: '91%', shadow: '82%' },
  { id: 'Submerged Pipe', type: 'Infrastructure', location: '15.499, 73.828', conf: '87%', shadow: '78%' },
  { id: 'Unknown Anomaly', type: 'Anomaly', location: '15.498, 73.827', conf: '89%', shadow: '31%' },
  { id: 'Shipwreck', type: 'Wreck', location: '15.498, 73.827', conf: '96%', shadow: '94%' },
];

export const SonarAnalysis: React.FC = () => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [analysisDone, setAnalysisDone] = useState<boolean>(false);

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    setImageSrc(url);
    setIsAnalyzing(true);
    setAnalysisDone(false);

    setTimeout(() => {
      setIsAnalyzing(false);
      setAnalysisDone(true);
    }, 1400);
  };

  const showSidePanel = imageSrc !== null;

  return (
    <div className={styles.container}>
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
                <button className={styles.iconBtn}><ZoomIn size={14} /></button>
                <button className={styles.iconBtn}><ZoomOut size={14} /></button>
                <button className={styles.iconBtn}><Maximize size={14} /></button>
                <button className={styles.layerToggle}><Layers size={13} /> ON</button>
              </div>
            </div>

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
                  <img src={imageSrc} alt="Sonar Scan" className={styles.sonarImage} />

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
                      <span>LAT <strong>15.498912</strong></span>
                      <span>LON <strong>73.827845</strong></span>
                      <span>HDG <strong>142.5°</strong></span>
                      <span>SPD <strong>4.2kt</strong></span>
                      <span>ALT <strong>12.4m</strong></span>
                      <span>RNG <strong>40m</strong></span>
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
                  {analysisDone && <span className={styles.countBadge}>2 Targets</span>}
                  {analysisDone && (
                    <button className={styles.exportBtn}><Download size={12} /> EXPORT JSON</button>
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
                      <div className={styles.detectionCardAlert}>
                        <div className={styles.cardMain}>
                          <span className={styles.targetTitle}>GHOST_NET</span>
                          <span className={styles.targetConfRed}>91% CONF</span>
                        </div>
                        <div className={styles.cardSub}>
                          <span>FRM: 0042</span>
                          <span className={styles.statusVerified}>VERIFIED</span>
                        </div>
                      </div>

                      <div className={styles.detectionCardWarn}>
                        <div className={styles.cardMain}>
                          <span className={styles.targetTitle}>SUB_PIPE</span>
                          <span className={styles.targetConfAmber}>84% CONF</span>
                        </div>
                        <div className={styles.cardSub}>
                          <span>FRM: 0038</span>
                          <span className={styles.statusReview}>REVIEW</span>
                        </div>
                      </div>
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
                      <div className={styles.metricRow}><span>Shadow Length</span><strong>4.2m</strong></div>
                      <div className={styles.metricRow}><span>Est. Height</span><strong>1.8m</strong></div>
                      <div className={styles.metricRow}><span>Geometry Score</span><strong className={styles.greenText}>82%</strong></div>
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
                      <div><small>FRAMES</small><h4>14,204</h4></div>
                      <div><small>TARGETS</small><h4>12</h4></div>
                      <div><small>VERIFIED</small><h4>4</h4></div>
                      <div><small>COVERAGE</small><h4>42%</h4></div>
                    </div>
                  )}
                </div>
              </div>

              {analysisDone && (
                <div className={styles.panelBlock}>
                  <div className={styles.panelBlockHeader}><span>TARGET CLASSIFICATION</span></div>
                  <div className={styles.panelBlockBody}>
                    <p className={styles.classificationSubtitle}>
                      4 TARGETS DETECTED · 3 VERIFIED · 1 REQUIRES REVIEW
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
                        {MOCK_TARGETS.map((row) => (
                          <tr key={row.id}>
                            <td>{row.id}</td>
                            <td>{row.type}</td>
                            <td>{row.location}</td>
                            <td>{row.conf}</td>
                            <td>{row.shadow}</td>
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