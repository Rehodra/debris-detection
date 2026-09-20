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

const defaultSampleTargets: MasterTargetResult[] = [
  {
    detection_id: 'TRK-042-01',
    class_id: 1,
    class_name: 'ghost_net',
    display_name: 'Entangled Net',
    category: 'HAZARDOUS DEBRIS',
    calibrated_confidence: 0.91,
    ai_confidence: 0.89,
    trust_tier: 'VERIFIED_TARGET',
    bbox: {
      x_min: 180,
      y_min: 160,
      x_max: 370,
      y_max: 320,
      width: 190,
      height: 160,
      normalized_x_min: 0.22,
      normalized_y_min: 0.20,
      normalized_x_max: 0.46,
      normalized_y_max: 0.40,
    },
    shadow_evidence: {
      has_shadow: true,
      shadow_score: 0.88,
      shadow_length_m: 4.2,
      estimated_height_m: 1.65,
      cardinal_direction: 'NE',
      direction_degrees: 45,
    },
    dimensions: {
      pixel_width: 190,
      pixel_height: 160,
      length_m: 3.4,
      width_m: 2.1,
      height_m: 1.65,
      across_track_m: 2.1,
      along_track_m: 3.4,
      slant_range_m: 28.5,
      ground_range_m: 26.2,
      area_sq_m: 7.14,
      estimated_volume_m3: 5.89,
      dry_mass_metric_tons: 1.2,
      submerged_weight_kn: 3.4,
      recommended_crane_lift_tons: 1.8,
      seabed_stability_index: 2.4,
      seabed_mobility_status: 'Settled / Stable',
      measurement_method: 'sonar_raster_geometry',
      measurement_status: 'verified_complete',
      warnings: [],
    },
    coordinates: { latitude: 10.48234, longitude: 80.21441 },
    georeference: {
      status: 'calculated',
      coordinate_reference: 'WGS84',
      latitude: 10.48234,
      longitude: 80.21441,
      source_ping_index: 142,
      waterfall_row: 142,
      across_track_pixel: 275,
      across_track_offset_m: 8.4,
      slant_range_m: 28.5,
      heading_deg: 90,
      layback_applied: false,
      warnings: [],
    },
    clearance: {
      water_depth_m: 28.0,
      object_height_m: 1.65,
      clearance_m: 26.35,
      threatens_shallow_draft: false,
      threatens_medium_draft: false,
      threatens_deep_draft: false,
    },
    risk_score: 85,
    risk_tier: 'HIGH',
    color_hex: '#ea580c',
  },
  {
    detection_id: 'TRK-042-02',
    class_id: 2,
    class_name: 'shipwreck',
    display_name: 'Shipwreck',
    category: 'MAJOR OBSTRUCTION',
    calibrated_confidence: 0.95,
    ai_confidence: 0.96,
    trust_tier: 'VERIFIED_TARGET',
    bbox: {
      x_min: 440,
      y_min: 360,
      x_max: 720,
      y_max: 560,
      width: 280,
      height: 200,
      normalized_x_min: 0.55,
      normalized_y_min: 0.45,
      normalized_x_max: 0.90,
      normalized_y_max: 0.70,
    },
    shadow_evidence: {
      has_shadow: true,
      shadow_score: 0.94,
      shadow_length_m: 8.5,
      estimated_height_m: 4.8,
      cardinal_direction: 'E',
      direction_degrees: 90,
    },
    dimensions: {
      pixel_width: 280,
      pixel_height: 200,
      length_m: 14.2,
      width_m: 6.5,
      height_m: 4.8,
      across_track_m: 6.5,
      along_track_m: 14.2,
      slant_range_m: 35.0,
      ground_range_m: 32.8,
      area_sq_m: 92.3,
      estimated_volume_m3: 221.5,
      dry_mass_metric_tons: 45.0,
      submerged_weight_kn: 320.0,
      recommended_crane_lift_tons: 67.5,
      seabed_stability_index: 4.5,
      seabed_mobility_status: 'Settled / Stable',
      measurement_method: 'sonar_raster_geometry',
      measurement_status: 'verified_complete',
      warnings: [],
    },
    coordinates: { latitude: 10.48292, longitude: 80.21528 },
    georeference: {
      status: 'calculated',
      coordinate_reference: 'WGS84',
      latitude: 10.48292,
      longitude: 80.21528,
      source_ping_index: 380,
      waterfall_row: 380,
      across_track_pixel: 580,
      across_track_offset_m: 16.2,
      slant_range_m: 35.0,
      heading_deg: 90,
      layback_applied: false,
      warnings: [],
    },
    clearance: {
      water_depth_m: 8.0,
      object_height_m: 4.8,
      clearance_m: 3.2,
      threatens_shallow_draft: true,
      threatens_medium_draft: true,
      threatens_deep_draft: true,
    },
    risk_score: 92,
    risk_tier: 'CRITICAL',
    color_hex: '#ef4444',
    action_recommendations: [
      {
        category: 'NAVIGATION',
        priority: 'IMMEDIATE',
        action_text: 'Broadcast Notice to Mariners (NOTMAR). Navigational clearance <= 3.5m threatens shallow draft vessels.',
        authority_standard: 'USCG / IMO NOTMAR',
      },
    ],
  },
];

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
  const [sampleIndex, setSampleIndex] = useState<number>(0);
  const [isDropzoneDragging, setIsDropzoneDragging] = useState<boolean>(false);

  const sampleFrames = ['/new.png', '/accident.jpg', '/2nd.jpg', '/3rd.jpg', '/4th.jpg'];

  const SAMPLE_SURVEYS = [
    { name: 'Survey Line 01: Multi-Debris Field', path: '/new.png', desc: 'Normalized acoustic mosaic with multiple target contacts' },
    { name: 'Survey Line 02: Shipwreck Contact', path: '/accident.jpg', desc: 'Acoustic shadow and structural debris contact' },
    { name: 'Survey Line 03: Channel Fairway A', path: '/2nd.jpg', desc: 'Acoustic sweep across fairway transit corridor' },
    { name: 'Survey Line 04: Fairway Obstruction B', path: '/3rd.jpg', desc: 'Seafloor anomaly in high acoustic backscatter sector' },
    { name: 'Survey Line 05: Deep Anchor Sector', path: '/4th.jpg', desc: 'Deep benthic survey sector with seabed hazards' },
  ];

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
        setSonarResponse(resp);
        const masterRes = resp.analysis;
        setAnalysis(masterRes);

        const missionId = resp.mission_id || masterRes.mission_id;
        const rasterUrl = getSonarRasterUrl(missionId);
        setImageSrc(rasterUrl);

        // Fetch ordered navigation track
        try {
          const track = await getSonarTrack(missionId);
          setNavigationTrack(track);
        } catch {
          // Track might be unavailable if sonar file lacked GPS packets
        }

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
      setImageSrc(localUrl);

      try {
        const masterRes = await analyzeSonarImage(file, vessel);
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

  const handleSelectSample = (index: number) => {
    setSampleIndex(index);
    setImageSrc(sampleFrames[index]);
    setIsRawSonar(false);
    setSelectedFile(null);
    setAnalysis(null);
    setSonarResponse(null);
    setNavigationTrack(null);
    setSelectedTargetId(defaultSampleTargets[0]?.detection_id ?? null);
    setError(null);
  };

  const analysisDone = analysis !== null;
  const missionId = sonarResponse?.mission_id || analysis?.mission_id || (imageSrc ? 'MSN-LOCAL-01' : null);
  const targets: MasterTargetResult[] = analysis?.targets ?? (imageSrc && !analysisDone ? defaultSampleTargets : []);
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
                onClick={() => handleSelectSample(0)}
                style={{ cursor: 'pointer' }}
                title="Click to load sample acoustic scan"
              >
                <img src="/new.png" alt="MarineScan Sonar Preview" />
                <span>SAMPLE RASTER VIEW</span>
                <i>Click to load in workstation</i>
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
                  activeFileName={
                    selectedFile?.name ||
                    (imageSrc ? (SAMPLE_SURVEYS[sampleIndex]?.name ?? `SURVEY_SAMPLE_0${sampleIndex + 1}`) : null)
                  }
                  samples={SAMPLE_SURVEYS}
                  onSelectSample={handleSelectSample}
                  selectedSampleIndex={selectedFile ? -1 : sampleIndex}
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
                  {hasTargets && (
                    <span className={styles.countBadge}>
                      {filteredTargets.length === targets.length
                        ? `${targets.length} Targets`
                        : `${filteredTargets.length} / ${targets.length}`}
                    </span>
                  )}
                </div>

                <div className={styles.panelBlockBody}>
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