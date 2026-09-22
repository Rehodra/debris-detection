import React, { useState, ChangeEvent, useEffect } from 'react';
import {
  Upload,
  RefreshCw,
  RotateCcw,
  Radar,
  Radio,
  FileCode,
  Compass,
} from 'lucide-react';
import styles from './SonarAnalysis.module.scss';
import {
  MasterTargetResult,
  MasterAnalysisResult,
  SonarAnalysisResponse,
  SonarNavigationTrack,
  VesselParams,
  analyzeSonarImage,
  analyzeSonarFile,
  clampVesselField,
  getSonarRasterUrl,
  getSonarTrack,
  isRawSonarFile,
} from '../api/client';
import WaterfallViewer from '../components/sonar/WaterfallViewer';
import SonarTrackMap from '../components/sonar/SonarTrackMap';
import TargetInspector from '../components/sonar/TargetInspector';
import SonarTelemetry from '../components/sonar/SonarTelemetry';
import ExportControls from '../components/sonar/ExportControls';

const DEFAULT_VESSEL: VesselParams = { vesselLat: 13.05, vesselLon: 80.42, vesselHeadingDeg: 90 };

export const SonarAnalysis: React.FC = () => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isRawSonar, setIsRawSonar] = useState<boolean>(false);
  const [analysis, setAnalysis] = useState<MasterAnalysisResult | null>(null);
  const [sonarResponse, setSonarResponse] = useState<SonarAnalysisResponse | null>(null);
  const [navigationTrack, setNavigationTrack] = useState<SonarNavigationTrack | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [vessel, setVessel] = useState<VesselParams>(DEFAULT_VESSEL);
  const [filter, setFilter] = useState<'all' | 'verified' | 'high_risk'>('all');
  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);
  const [showLayers, setShowLayers] = useState<boolean>(true);
  const [isDropzoneDragging, setIsDropzoneDragging] = useState<boolean>(false);

  const processUploadedFile = async (file: File) => {
    setSelectedFile(file);
    setError(null);
    setAnalysis(null);
    setSonarResponse(null);
    setNavigationTrack(null);
    setSelectedTargetId(null);
    setIsAnalyzing(true);

    const isRaw = isRawSonarFile(file);
    setIsRawSonar(isRaw);

    if (isRaw) {
      // Raw binary sonar (.xtf / .jsf)
      setImageSrc(null); // Clear until backend raster is ready
      try {
        const resp = await analyzeSonarFile(file, vessel);
        const masterRes = resp.analysis;
        const missionId = resp.mission_id || masterRes.mission_id;
        const rasterUrl = getSonarRasterUrl(missionId);

        // Preload raster image so it renders immediately
        await new Promise<void>((resolve) => {
          const img = new Image();
          img.onload = () => resolve();
          img.onerror = () => resolve();
          img.src = rasterUrl;
        });

        // 1. Show the sonar raster image FIRST in the viewer!
        setImageSrc(rasterUrl);
        setSonarResponse(resp);

        // Fetch ordered navigation track in parallel
        try {
          const track = await getSonarTrack(missionId);
          setNavigationTrack(track);
        } catch {
          // Track might be unavailable
        }

        // 2. Allow user to watch the acoustic sweep scan over the sonar waterfall
        await new Promise((resolve) => setTimeout(resolve, 1600));

        // 3. ONLY AFTER the scan completes, reveal the detection results!
        setAnalysis(masterRes);
        if (masterRes.targets?.length > 0) {
          setSelectedTargetId(masterRes.targets[0].detection_id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Raw sonar analysis failed');
      } finally {
        setIsAnalyzing(false);
      }
    } else {
      // Conventional image upload (.png, .jpg, .tiff, etc.)
      const localUrl = URL.createObjectURL(file);
      // 1. Show the sonar image FIRST!
      setImageSrc(localUrl);

      try {
        // 2. Run API detection and minimum 1.6s scan animation in parallel
        const [masterRes] = await Promise.all([
          analyzeSonarImage(file, vessel),
          new Promise((resolve) => setTimeout(resolve, 1600)),
        ]);

        // 3. ONLY AFTER the scan completes, reveal the detection results!
        setAnalysis(masterRes);
        if (masterRes.targets?.length > 0) {
          setSelectedTargetId(masterRes.targets[0].detection_id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Image analysis failed');
      } finally {
        setIsAnalyzing(false);
      }
    }
  };

  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await processUploadedFile(file);
    e.target.value = '';
  };


  const analysisDone = analysis !== null;
  const missionId = sonarResponse?.mission_id || analysis?.mission_id || (imageSrc ? 'MSN-LOCAL-01' : null);
  // Only show targets from actual analysis; never fall back to static default data!
  const targets: MasterTargetResult[] = isAnalyzing ? [] : (analysis?.targets ?? []);
  const hasTargets = targets.length > 0;

  const verifiedCount = targets.filter((t) => t.trust_tier === 'VERIFIED_TARGET').length;
  const highRiskCount = targets.filter((t) => t.risk_tier === 'CRITICAL' || t.risk_tier === 'HIGH').length;

  const filteredTargets = targets.filter((target) => {
    if (filter === 'verified') return target.trust_tier === 'VERIFIED_TARGET';
    if (filter === 'high_risk') return target.risk_tier === 'CRITICAL' || target.risk_tier === 'HIGH';
    return true;
  });

  const activeTarget = targets.find((t) => t.detection_id === selectedTargetId) ?? targets[0] ?? null;

  const formatTargetType = (target: MasterTargetResult) => target.class_name.replace('_', ' ').toUpperCase();

  const getClassBadgeClass = (className: string) => {
    switch (className.toLowerCase()) {
      case 'shipwreck':
        return styles.badgeShipwreck;
      case 'pipe':
        return styles.badgePipe;
      case 'ghost_net':
        return styles.badgeGhostNet;
      case 'marine_debris':
        return styles.badgeDebris;
      case 'aircraft':
        return styles.badgeAircraft;
      case 'fish':
        return styles.badgeFish;
      default:
        return styles.badgeOther;
    }
  };

  const getRiskBadgeClass = (riskTier: string) => {
    switch (riskTier?.toUpperCase()) {
      case 'CRITICAL':
        return styles.riskCritical;
      case 'HIGH':
        return styles.riskHigh;
      case 'MODERATE':
        return styles.riskModerate;
      default:
        return styles.riskLow;
    }
  };

  const handleResetWorkspace = () => {
    setImageSrc(null);
    setSelectedFile(null);
    setIsRawSonar(false);
    setAnalysis(null);
    setSonarResponse(null);
    setNavigationTrack(null);
    setIsAnalyzing(false);
    setError(null);
    setSelectedTargetId(null);
    setFilter('all');
  };

  const showWorkspace = imageSrc !== null || isAnalyzing;

  return (
    <div className={`${styles.container} sonar-page page-enter`}>
      {/* Top Telemetry & Header Bar */}
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          <div className={styles.vesselInputGroup}>
            <span className={styles.vesselLabel}>LAT</span>
            <input
              className={styles.vesselInput}
              type="number"
              step="0.0001"
              min={-90}
              max={90}
              value={vessel.vesselLat}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, 'vesselLat');
                setVessel((v) => ({ ...v, vesselLat: clamped }));
              }}
              style={{ width: '64px' }}
            />
            <span className={styles.vesselUnit}>°N</span>
          </div>
          <span className={styles.divider}>|</span>
          <div className={styles.vesselInputGroup}>
            <span className={styles.vesselLabel}>LON</span>
            <input
              className={styles.vesselInput}
              type="number"
              step="0.0001"
              min={-180}
              max={180}
              value={vessel.vesselLon}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, 'vesselLon');
                setVessel((v) => ({ ...v, vesselLon: clamped }));
              }}
              style={{ width: '68px' }}
            />
            <span className={styles.vesselUnit}>°E</span>
          </div>
          <span className={styles.divider}>|</span>
          <div className={styles.vesselInputGroup}>
            <span className={styles.vesselLabel}>HDG</span>
            <input
              className={styles.vesselInput}
              type="number"
              step="1"
              min={0}
              max={359}
              value={vessel.vesselHeadingDeg}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, 'vesselHeadingDeg');
                setVessel((v) => ({ ...v, vesselHeadingDeg: clamped }));
              }}
              style={{ width: '42px' }}
            />
            <span className={styles.vesselUnit}>°</span>
          </div>
        </div>
        <div className={styles.statusBadges}>
          <span className={styles.statusDot}>
            <i className={styles.dotGreen} /> SONAR ONLINE
          </span>
          <span className={styles.statusDot}>
            <i className={styles.dotGreen} /> GPS FIX
          </span>
          <span className={isRawSonar ? styles.badgeSuccess : styles.badgeDanger}>
            {isRawSonar ? 'RAW SONAR (XTF/JSF)' : 'CONVENTIONAL / RASTER'}
          </span>

          {/* Persistent Workstation Header Reset Button */}
          {showWorkspace && (
            <button
              type="button"
              className={styles.headerResetBtn}
              onClick={handleResetWorkspace}
              title="Clear current survey analysis and return to intake dropzone"
            >
              <RotateCcw size={11} />
              <span>RESET</span>
            </button>
          )}

          {/* Persistent Workstation Header Upload Button */}
          <label
            className={styles.headerUploadBtn}
            title="Upload new survey imagery (.PNG/.JPG/.TIFF) or raw sonar binary (.XTF/.JSF)"
          >
            <Upload size={12} />
            <span>NEW SURVEY</span>
            <input
              type="file"
              accept="image/*,.xtf,.jsf,.tif,.tiff"
              onChange={handleFileUpload}
              style={{ display: 'none' }}
            />
          </label>
        </div>
      </header>

      {/* Main Workspace Area */}
      <div className={styles.scrollArea}>
        {!showWorkspace ? (
          /* Empty / Upload Dropzone State */
          <div className={styles.emptyWorkspace}>
            <aside className={styles.emptyInputColumn}>
              <label
                htmlFor="sonar-upload"
                className={`${styles.uploadDropzone} ${isDropzoneDragging ? styles.uploadDropzoneActive : ''}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) processUploadedFile(file);
                }}
              >
                <div className={styles.uploadIconWrap}>
                  <Upload size={24} />
                </div>
                <span className={styles.uploadEyebrow}>MISSION INPUT</span>
                <h3>Upload Sonar or Mission Recording</h3>
                <p>Drag & drop a survey file here, or click to browse filesystem.</p>
                <div className={styles.uploadFormatTags}>
                  <span className={styles.tagImagery}>.PNG / .JPG / .TIFF (Imagery)</span>
                  <span className={styles.tagSonar}>.XTF / .JSF (Raw Sonar)</span>
                </div>
                <input
                  type="file"
                  id="sonar-upload"
                  accept="image/*,.xtf,.jsf,.tif,.tiff"
                  onChange={handleFileUpload}
                  hidden
                />
              </label>
              <div className={styles.missionMeta}>
                <span>WORKSTATION READY</span>
                <b>SUPPORTED PROTOCOLS</b>
                <strong>EdgeTech JSF & Triton XTF</strong>
                <b>PROCESSING PIPELINE</b>
                <strong>12-Stage Hydrographic Intelligence</strong>
              </div>
            </aside>

            <div className={styles.previewPanel}>
              <div className={styles.previewTabs}>
                <span className={styles.activeTab}>RAW SONAR WATERFALL</span>
                <span>YOLO11 DEBRIS DETECTION</span>
                <span>GEODESY & NOTMAR</span>
              </div>
              <div
                className={styles.previewImage}
                onClick={() => {
                  const input = document.getElementById('sonar-upload') as HTMLInputElement;
                  input?.click();
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(false);
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDropzoneDragging(false);
                  const file = e.dataTransfer.files?.[0];
                  if (file) processUploadedFile(file);
                }}
                style={{ cursor: 'pointer' }}
                title="Click or drop survey file to upload and begin analysis"
              >
                <div className={styles.previewImagePlaceholder}>
                  <Radar size={32} />
                  <span>UPLOAD RASTER OR SONAR FILE</span>
                  <i>Click or drop photo here to analyze</i>
                </div>
              </div>
              <div className={styles.previewNote}>
                <strong>ACOUSTIC ANALYSIS WORKSTATION</strong>
                <p>
                  Decode ping records, assemble normalized waterfalls, identify underwater debris with
                  shadow corroboration, calculate 3D dimensions, and evaluate NOTMAR navigational hazard risks.
                </p>
              </div>
            </div>

            <aside className={styles.emptyDetections}>
              <div className={styles.emptyDetections__header}>
                <strong>DETECTABLE HAZARDS</strong>
                <span>Trained 7-Class Model</span>
              </div>
              {[
                'Shipwreck',
                'Subsea Pipeline',
                'Ghost Net',
                'Marine Debris',
                'Aircraft Wreckage',
              ].map((name, index) => (
                <div className={styles.emptyDetection} key={`${name}-${index}`}>
                  <i />
                  <span>
                    <b>{name}</b>
                    <small>Class #{index + 1}</small>
                  </span>
                  <strong>{[95, 88, 91, 84, 96][index]}%</strong>
                </div>
              ))}
            </aside>
          </div>
        ) : (
          /* Active Workstation Layout */
          <div className={styles.mainContent}>
            {/* Left Column: Waterfall Viewer + Navigation Track Map */}
            <div className={styles.visualizationColumn}>
              {/* Sonar Waterfall Viewer */}
              <div className={styles.waterfallViewerWrap}>
                <WaterfallViewer
                  imageSrc={imageSrc}
                  isRawSonar={isRawSonar}
                  isLoading={isAnalyzing}
                  error={error}
                  rasterMeta={sonarResponse?.sonar || analysis?.sonar_metadata}
                  targets={targets}
                  selectedTargetId={selectedTargetId}
                  onSelectTarget={setSelectedTargetId}
                  showLayers={showLayers}
                  onToggleLayers={() => setShowLayers((prev) => !prev)}
                  onRetry={() => {
                    if (selectedFile) {
                      processUploadedFile(selectedFile);
                    }
                  }}
                  onUploadFile={processUploadedFile}
                  activeFileName={selectedFile?.name || 'Sonar Survey Recording'}
                />
              </div>

              {/* Navigation Track Map */}
              <div className={styles.mapBlock}>
                <SonarTrackMap
                  track={navigationTrack}
                  targets={targets}
                  selectedTargetId={selectedTargetId}
                  onSelectTarget={setSelectedTargetId}
                  vesselFix={{ latitude: vessel.vesselLat, longitude: vessel.vesselLon }}
                />
              </div>
            </div>

            {/* Right Column: Detections List, Target Inspector, Telemetry, Exports */}
            <div className={styles.sidePanel}>
              {/* Detection List */}
              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}>
                  <span className={styles.headerTitle}>
                    <Radar size={13} /> DETECTION TARGETS
                  </span>
                  {hasTargets && !isAnalyzing && (
                    <span className={styles.countBadge}>
                      {filteredTargets.length === targets.length
                        ? `${targets.length} Targets`
                        : `${filteredTargets.length} / ${targets.length}`}
                    </span>
                  )}
                  {isAnalyzing && (
                    <span className={styles.scanningBadge}>
                      ACOUSTIC SCAN ACTIVE
                    </span>
                  )}
                </div>

                <div className={styles.panelBlockBody}>
                  {isAnalyzing ? (
                    <div className={styles.scanningPanelState}>
                      <div className={styles.scanningRadarWrap}>
                        <Radar size={28} className={styles.scanRadarPulse} />
                      </div>
                      <h4>ANALYZING SONAR SCAN</h4>
                      <p>Scanning acoustic waterfall and running neural debris detection...</p>
                      <div className={styles.scanProgressTrack}>
                        <div className={styles.scanProgressBar} />
                      </div>
                      <div className={styles.scanStepList}>
                        <span>✓ Sonar Raster Loaded</span>
                        <span className={styles.scanStepActive}>• YOLO11 Target Classification</span>
                        <span>• 3D Shadow Corroboration</span>
                      </div>
                    </div>
                  ) : (
                    <>
                      {/* Filter Chips */}
                      <div className={styles.filterRow}>
                    <button
                      type="button"
                      className={`${styles.filterChip} ${filter === 'all' ? styles.filterChipActive : ''}`}
                      onClick={() => setFilter('all')}
                    >
                      ALL ({targets.length})
                    </button>
                    <button
                      type="button"
                      className={`${styles.filterChip} ${filter === 'verified' ? styles.filterChipActive : ''}`}
                      onClick={() => setFilter('verified')}
                    >
                      VERIFIED ({verifiedCount})
                    </button>
                    <button
                      type="button"
                      className={`${styles.filterChip} ${filter === 'high_risk' ? styles.filterChipActive : ''}`}
                      onClick={() => setFilter('high_risk')}
                    >
                      HIGH RISK ({highRiskCount})
                    </button>
                  </div>

                  {/* Target Cards List */}
                  <div className={styles.targetCardsList}>
                    {filteredTargets.map((target) => {
                      const originalIndex = targets.findIndex((t) => t.detection_id === target.detection_id);
                      const isSelected = activeTarget?.detection_id === target.detection_id;

                      return (
                        <div
                          key={target.detection_id}
                          className={`${styles.detectionCard} ${
                            target.risk_tier === 'CRITICAL' || target.risk_tier === 'HIGH'
                              ? styles.detectionCardAlert
                              : styles.detectionCardWarn
                          } ${isSelected ? styles.detectionCardSelected : ''}`}
                          onClick={() => setSelectedTargetId(target.detection_id)}
                          role="button"
                          tabIndex={0}
                        >
                          <div className={styles.cardHeader}>
                            <div className={styles.cardHeaderLeft}>
                              <span className={styles.targetIndexBadge}>
                                #{String(originalIndex + 1).padStart(2, '0')}
                              </span>
                              <span className={`${styles.classBadge} ${getClassBadgeClass(target.class_name)}`}>
                                {formatTargetType(target)}
                              </span>
                            </div>
                            <span
                              className={
                                target.calibrated_confidence >= 0.8
                                  ? styles.targetConfRed
                                  : styles.targetConfAmber
                              }
                            >
                              {Math.round(target.calibrated_confidence * 100)}% CONF
                            </span>
                          </div>

                          <div className={styles.cardMetaGrid}>
                            <div className={styles.metaCell}>
                              <span className={styles.metaLabel}>SIZE</span>
                              <span className={styles.metaValue}>
                                {target.dimensions?.length_m?.toFixed(1) ?? '—'} × {target.dimensions?.width_m?.toFixed(1) ?? '—'}m
                              </span>
                            </div>
                            <div className={styles.metaCell}>
                              <span className={styles.metaLabel}>HEIGHT</span>
                              <span className={styles.metaValue}>
                                {target.shadow_evidence?.estimated_height_m != null
                                  ? `+${target.shadow_evidence.estimated_height_m.toFixed(2)}m`
                                  : '—'}
                              </span>
                            </div>
                            <div className={styles.metaCell}>
                              <span className={styles.metaLabel}>COORDS</span>
                              <span className={styles.metaValue}>
                                {target.coordinates?.latitude != null
                                  ? `${target.coordinates.latitude.toFixed(3)}°, ${target.coordinates.longitude.toFixed(3)}°`
                                  : 'Unavailable'}
                              </span>
                            </div>
                            <div className={styles.metaCell}>
                              <span className={styles.metaLabel}>SHADOW</span>
                              <span className={styles.metaValue}>
                                {Math.round(target.shadow_evidence.shadow_score * 100)}%
                              </span>
                            </div>
                          </div>

                          <div className={styles.cardFooter}>
                            <span className={`${styles.riskBadge} ${getRiskBadgeClass(target.risk_tier)}`}>
                              {target.risk_tier} RISK ({Math.round(target.risk_score)})
                            </span>
                            <span
                              className={
                                target.trust_tier === 'VERIFIED_TARGET'
                                  ? styles.statusVerified
                                  : styles.statusReview
                              }
                            >
                              {target.trust_tier.replace(/_/g, ' ')}
                            </span>
                          </div>
                        </div>
                      );
                    })}

                    {filteredTargets.length === 0 && targets.length > 0 && (
                      <div className={styles.emptyFilteredState}>
                        <p>No targets match the active filter.</p>
                        <button type="button" className={styles.resetFilterBtn} onClick={() => setFilter('all')}>
                          Show All Targets
                        </button>
                      </div>
                    )}

                    {targets.length === 0 && !isAnalyzing && (
                      <div className={styles.noTargetsState}>
                        <p>No acoustic anomalies or debris detected in this scan.</p>
                      </div>
                    )}
                  </div>
                    </>
                  )}
                </div>
              </div>

              {/* Target Inspector (Dimensions, Geodesy, Risk & NOTMAR) */}
              <div className={styles.inspectorWrap}>
                <TargetInspector target={activeTarget} />
              </div>

              {/* Telemetry Panel */}
              <SonarTelemetry
                navigation={sonarResponse?.navigation || analysis?.sonar_metadata?.navigation}
                sonarMeta={sonarResponse?.sonar || analysis?.sonar_metadata}
                source={sonarResponse?.source}
              />

              {/* Hydrographic Export Controls */}
              <ExportControls
                analysisId={missionId}
                hasTrack={navigationTrack !== null && navigationTrack.points.length > 0}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SonarAnalysis;