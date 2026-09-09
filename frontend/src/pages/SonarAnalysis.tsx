import React, { useState, ChangeEvent, useRef, useEffect, useCallback } from 'react';
import {
  Upload, Download, Radio, MapPin, RefreshCw, ScanLine,
  ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Maximize, Minimize2, RotateCcw, Layers,
  CheckCircle2, Circle, FileJson, FileSpreadsheet, Radar
} from 'lucide-react';
import styles from './SonarAnalysis.module.scss';
import { AnalysisTarget, MasterAnalysisResult, VesselParams, analyzeSonarImage, clampVesselField, downloadAnalysisReport, resolveApiAssetUrl } from '../api/client';

/* A real Bay-of-Bengal point off Chennai (matches the Detection Map page's
   default). Without a real vessel fix the backend falls back to a hardcoded
   point off Karachi, Pakistan — every detection through this page used to
   geolocate there regardless of where the survey actually happened. */
const DEFAULT_VESSEL: VesselParams = { vesselLat: 13.05, vesselLon: 80.42, vesselHeadingDeg: 90 };

const defaultSampleTargets: AnalysisTarget[] = [
  {
    detection_id: 'TRK-042-01',
    class_name: 'ghost_net',
    display_name: 'Entangled Net',
    calibrated_confidence: 0.91,
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
    },
    dimensions: { length_m: 3.4, width_m: 2.1, height_m: 1.65 },
    coordinates: { latitude: 10.48234, longitude: 80.21441 },
    risk_score: 85,
    risk_tier: 'HIGH',
  },
  {
    detection_id: 'TRK-042-02',
    class_name: 'shipwreck',
    display_name: 'Shipwreck',
    calibrated_confidence: 0.95,
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
      estimated_height_m: 3.8,
    },
    dimensions: { length_m: 14.2, width_m: 6.5, height_m: 3.8 },
    coordinates: { latitude: 10.48292, longitude: 80.21528 },
    risk_score: 92,
    risk_tier: 'CRITICAL',
  },
];

export const SonarAnalysis: React.FC = () => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<MasterAnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [vessel, setVessel] = useState<VesselParams>(DEFAULT_VESSEL);
  const [filter, setFilter] = useState<'all' | 'verified' | 'high_risk'>('all');
  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);

  // Robust Viewport & Transform State
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [baseSize, setBaseSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isAnimating, setIsAnimating] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showLayers, setShowLayers] = useState<boolean>(true);
  const [sampleIndex, setSampleIndex] = useState<number>(0);

  const sampleFrames = ['/new.png', '/accident.jpg', '/2nd.jpg', '/3rd.jpg', '/4th.jpg'];

  const viewportRef = useRef<HTMLDivElement>(null);
  const viewerPanelRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const isDraggingRef = useRef<boolean>(false);
  const dragStartRef = useRef<{ clientX: number; clientY: number; panX: number; panY: number }>({
    clientX: 0,
    clientY: 0,
    panX: 0,
    panY: 0,
  });

  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const panRef = useRef(pan);
  panRef.current = pan;
  const baseSizeRef = useRef(baseSize);
  baseSizeRef.current = baseSize;

  const clampPan = useCallback(
    (
      testPanX: number,
      testPanY: number,
      targetZoom: number,
      baseW: number,
      baseH: number,
      vpW: number,
      vpH: number
    ) => {
      if (baseW <= 0 || baseH <= 0 || vpW <= 0 || vpH <= 0) {
        return { x: 0, y: 0 };
      }

      const scaledW = baseW * targetZoom;
      const scaledH = baseH * targetZoom;

      const footerHeight = 44;
      const effectiveVpH = Math.max(vpH - footerHeight, 60);

      let minX: number;
      let maxX: number;
      if (scaledW > vpW) {
        minX = vpW - scaledW;
        maxX = 0;
      } else {
        minX = (vpW - scaledW) / 2;
        maxX = minX;
      }

      let minY: number;
      let maxY: number;
      if (scaledH > effectiveVpH) {
        minY = effectiveVpH - scaledH;
        maxY = 0;
      } else {
        minY = Math.max(0, (effectiveVpH - scaledH) / 2);
        maxY = minY;
      }

      return {
        x: Math.min(Math.max(testPanX, minX), maxX),
        y: Math.min(Math.max(testPanY, minY), maxY),
      };
    },
    []
  );

  const updateDimensions = useCallback(
    (newNatW?: number, newNatH?: number) => {
      if (!viewportRef.current) return;
      const rect = viewportRef.current.getBoundingClientRect();
      const vpW = rect.width;
      const vpH = rect.height;
      if (vpW <= 0 || vpH <= 0) return;

      const natW = newNatW ?? naturalSize.width;
      const natH = newNatH ?? naturalSize.height;
      if (natW <= 0 || natH <= 0) return;

      const footerHeight = 44;
      const effectiveVpH = Math.max(vpH - footerHeight, 60);

      const fitScale = Math.min(vpW / natW, effectiveVpH / natH);
      const baseW = Math.max(1, Math.round(natW * fitScale));
      const baseH = Math.max(1, Math.round(natH * fitScale));

      setBaseSize({ width: baseW, height: baseH });

      setPan((currPan) => {
        if (zoomRef.current <= 1.001) {
          return {
            x: (vpW - baseW) / 2,
            y: Math.max(0, (effectiveVpH - baseH) / 2),
          };
        }
        return clampPan(currPan.x, currPan.y, zoomRef.current, baseW, baseH, vpW, vpH);
      });
    },
    [naturalSize.width, naturalSize.height, clampPan]
  );

  useEffect(() => {
    const handleFullscreenChange = () => {
      const isFull = !!(document.fullscreenElement || (document as any).webkitFullscreenElement);
      setIsFullscreen(isFull);
      setTimeout(() => updateDimensions(), 80);
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
    };
  }, [updateDimensions]);

  useEffect(() => {
    if (!viewportRef.current) return;
    const ro = new ResizeObserver(() => {
      updateDimensions();
    });
    ro.observe(viewportRef.current);
    return () => ro.disconnect();
  }, [updateDimensions]);

  useEffect(() => {
    if (imageRef.current && imageRef.current.complete && imageRef.current.naturalWidth > 0) {
      const natW = imageRef.current.naturalWidth;
      const natH = imageRef.current.naturalHeight;
      setNaturalSize({ width: natW, height: natH });
      updateDimensions(natW, natH);
    }
  }, [imageSrc, updateDimensions]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current || !viewportRef.current) return;
      const dx = e.clientX - dragStartRef.current.clientX;
      const dy = e.clientY - dragStartRef.current.clientY;

      const rect = viewportRef.current.getBoundingClientRect();
      const clamped = clampPan(
        dragStartRef.current.panX + dx,
        dragStartRef.current.panY + dy,
        zoomRef.current,
        baseSizeRef.current.width,
        baseSizeRef.current.height,
        rect.width,
        rect.height
      );
      setPan(clamped);
    };

    const handleMouseUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false;
        setIsDragging(false);
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [clampPan]);

  // Non-passive wheel event listener to completely block page scrolling when zooming/panning inside viewer
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    const onWheelNative = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const bs = baseSizeRef.current;
      if (bs.width <= 0 || bs.height <= 0) return;
      const rect = el.getBoundingClientRect();

      const isPinch = e.ctrlKey;
      const isWheelZoom = !e.shiftKey && Math.abs(e.deltaY) > 0 && Math.abs(e.deltaX) === 0;

      if (isPinch || isWheelZoom) {
        const cursorX = e.clientX - rect.left;
        const cursorY = e.clientY - rect.top;

        const zoomDelta = e.deltaY < 0 ? 1.15 : 0.87;
        const newZoom = Math.min(8.0, Math.max(1.0, Number((zoomRef.current * zoomDelta).toFixed(3))));

        if (Math.abs(newZoom - zoomRef.current) < 0.001) return;

        const contentX = (cursorX - panRef.current.x) / zoomRef.current;
        const contentY = (cursorY - panRef.current.y) / zoomRef.current;
        const newPanX = cursorX - contentX * newZoom;
        const newPanY = cursorY - contentY * newZoom;

        const clamped = clampPan(newPanX, newPanY, newZoom, bs.width, bs.height, rect.width, rect.height);
        setIsAnimating(false);
        setZoom(newZoom);
        setPan(clamped);
      } else {
        if (zoomRef.current > 1.0) {
          const dx = e.shiftKey ? -e.deltaY : -e.deltaX;
          const dy = e.shiftKey ? 0 : -e.deltaY;
          const clamped = clampPan(
            panRef.current.x + dx,
            panRef.current.y + dy,
            zoomRef.current,
            bs.width,
            bs.height,
            rect.width,
            rect.height
          );
          setIsAnimating(false);
          setPan(clamped);
        }
      }
    };

    el.addEventListener('wheel', onWheelNative, { passive: false });
    return () => {
      el.removeEventListener('wheel', onWheelNative);
    };
  }, [clampPan]);

  const handleImageLoad = (e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const natW = img.naturalWidth || 800;
    const natH = img.naturalHeight || 600;
    setNaturalSize({ width: natW, height: natH });
    updateDimensions(natW, natH);
  };

  const handleZoomIn = () => {
    if (!viewportRef.current || baseSize.width <= 0) return;
    const rect = viewportRef.current.getBoundingClientRect();
    const newZoom = Math.min(8.0, Number((zoom * 1.3).toFixed(2)));
    const centerX = rect.width / 2;
    const centerY = Math.max(0, (rect.height - 44) / 2);

    const contentX = (centerX - pan.x) / zoom;
    const contentY = (centerY - pan.y) / zoom;
    const newPanX = centerX - contentX * newZoom;
    const newPanY = centerY - contentY * newZoom;

    setIsAnimating(true);
    setZoom(newZoom);
    setPan(clampPan(newPanX, newPanY, newZoom, baseSize.width, baseSize.height, rect.width, rect.height));
  };

  const handleZoomOut = () => {
    if (!viewportRef.current || baseSize.width <= 0) return;
    const rect = viewportRef.current.getBoundingClientRect();
    const newZoom = Math.max(1.0, Number((zoom / 1.3).toFixed(2)));
    const centerX = rect.width / 2;
    const centerY = Math.max(0, (rect.height - 44) / 2);

    const contentX = (centerX - pan.x) / zoom;
    const contentY = (centerY - pan.y) / zoom;
    const newPanX = centerX - contentX * newZoom;
    const newPanY = centerY - contentY * newZoom;

    setIsAnimating(true);
    setZoom(newZoom);
    setPan(clampPan(newPanX, newPanY, newZoom, baseSize.width, baseSize.height, rect.width, rect.height));
  };

  const handleResetZoom = () => {
    if (!viewportRef.current || baseSize.width <= 0) {
      setZoom(1.0);
      setPan({ x: 0, y: 0 });
      return;
    }
    const rect = viewportRef.current.getBoundingClientRect();
    const effectiveVpH = Math.max(rect.height - 44, 60);
    setIsAnimating(true);
    setZoom(1.0);
    setPan({
      x: (rect.width - baseSize.width) / 2,
      y: Math.max(0, (effectiveVpH - baseSize.height) / 2),
    });
  };

  const toggleFullscreen = async () => {
    try {
      const panel = viewerPanelRef.current;
      if (!panel) return;

      const isFull = !!(document.fullscreenElement || (document as any).webkitFullscreenElement);
      if (!isFull) {
        if (panel.requestFullscreen) {
          await panel.requestFullscreen();
        } else if ((panel as any).webkitRequestFullscreen) {
          await (panel as any).webkitRequestFullscreen();
        } else {
          setIsFullscreen(true);
        }
      } else {
        if (document.exitFullscreen) {
          await document.exitFullscreen();
        } else if ((document as any).webkitExitFullscreen) {
          await (document as any).webkitExitFullscreen();
        } else {
          setIsFullscreen(false);
        }
      }
    } catch (err) {
      console.warn('Fullscreen toggle failed:', err);
      setIsFullscreen((prev) => !prev);
    }
    setTimeout(() => updateDimensions(), 100);
  };

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const targetEl = e.target as HTMLElement;
    if (targetEl.closest(`.${styles.imageMetaFooter}`) || targetEl.closest('button') || targetEl.closest('label')) {
      return;
    }

    if (zoomRef.current <= 1.0) return;

    e.preventDefault();
    isDraggingRef.current = true;
    setIsDragging(true);
    setIsAnimating(false);
    dragStartRef.current = {
      clientX: e.clientX,
      clientY: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };
  };

  const handleDoubleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const targetEl = e.target as HTMLElement;
    if (targetEl.closest(`.${styles.imageMetaFooter}`) || targetEl.closest('button') || targetEl.closest('label')) {
      return;
    }
    if (zoom > 1.05) {
      handleResetZoom();
    } else {
      if (!viewportRef.current || baseSize.width <= 0) return;
      const rect = viewportRef.current.getBoundingClientRect();
      const cursorX = e.clientX - rect.left;
      const cursorY = e.clientY - rect.top;
      const newZoom = 2.5;

      const contentX = (cursorX - pan.x) / zoom;
      const contentY = (cursorY - pan.y) / zoom;
      const newPanX = cursorX - contentX * newZoom;
      const newPanY = cursorY - contentY * newZoom;

      setIsAnimating(true);
      setZoom(newZoom);
      setPan(clampPan(newPanX, newPanY, newZoom, baseSize.width, baseSize.height, rect.width, rect.height));
    }
  };

  const handlePrevSample = () => {
    const nextIdx = (sampleIndex - 1 + sampleFrames.length) % sampleFrames.length;
    setSampleIndex(nextIdx);
    setImageSrc(sampleFrames[nextIdx]);
    setAnalysis(null);
    setSelectedTargetId(null);
    handleResetZoom();
  };

  const handleNextSample = () => {
    const nextIdx = (sampleIndex + 1) % sampleFrames.length;
    setSampleIndex(nextIdx);
    setImageSrc(sampleFrames[nextIdx]);
    setAnalysis(null);
    setSelectedTargetId(null);
    handleResetZoom();
  };

  const handleFileUpload = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const url = URL.createObjectURL(file);
    setImageSrc(url);
    setSelectedFile(file);
    setAnalysis(null);
    setSelectedTargetId(null);
    setError(null);
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    setIsAnalyzing(true);

    analyzeSonarImage(file, vessel)
      .then(setAnalysis)
      .catch((err: Error) => setError(err.message))
      .finally(() => setIsAnalyzing(false));
  };

  const analysisDone = analysis !== null;
  const targets = analysis?.targets ?? [];
  const displayTargets: AnalysisTarget[] = targets.length > 0
    ? targets
    : (imageSrc && !analysisDone ? defaultSampleTargets : []);
  const hasTargets = displayTargets.length > 0;
  const rawImage = imageSrc;
  const displayImage = rawImage;

  const verifiedCount = displayTargets.filter((t) => t.trust_tier === 'VERIFIED_TARGET').length;
  const highRiskCount = displayTargets.filter((t) => t.risk_tier === 'CRITICAL' || t.risk_tier === 'HIGH').length;

  const filteredTargets = displayTargets.filter((target) => {
    if (filter === 'verified') return target.trust_tier === 'VERIFIED_TARGET';
    if (filter === 'high_risk') return target.risk_tier === 'CRITICAL' || target.risk_tier === 'HIGH';
    return true;
  });

  const activeTarget = displayTargets.find((t) => t.detection_id === selectedTargetId) ?? displayTargets[0];

  const handleExport = async (format: 'json' | 'csv') => {
    if (!analysis && !selectedFile) return;
    setIsExporting(true);
    try {
      if (analysis) {
        if (format === 'json') {
          const jsonBlob = new Blob([JSON.stringify(analysis, null, 2)], {
            type: 'application/json',
          });
          const url = URL.createObjectURL(jsonBlob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${analysis.mission_id || 'marinescan'}_report.json`;
          link.click();
          URL.revokeObjectURL(url);
        } else {
          const headers = [
            'mission_id',
            'detection_id',
            'target_index',
            'class_name',
            'display_name',
            'calibrated_confidence',
            'trust_tier',
            'latitude',
            'longitude',
            'length_m',
            'width_m',
            'height_m',
            'shadow_score',
            'shadow_length_m',
            'estimated_height_m',
            'risk_score',
            'risk_tier',
          ];
          const rows = analysis.targets.map((t, idx) => [
            analysis.mission_id,
            t.detection_id,
            idx + 1,
            t.class_name,
            t.display_name,
            t.calibrated_confidence,
            t.trust_tier,
            t.coordinates?.latitude ?? '',
            t.coordinates?.longitude ?? '',
            t.dimensions?.length_m ?? '',
            t.dimensions?.width_m ?? '',
            t.dimensions?.height_m ?? '',
            t.shadow_evidence?.shadow_score ?? '',
            t.shadow_evidence?.shadow_length_m ?? '',
            t.shadow_evidence?.estimated_height_m ?? '',
            t.risk_score,
            t.risk_tier,
          ].map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
          const csvContent = [headers.join(','), ...rows].join('\r\n');
          const csvBlob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
          const url = URL.createObjectURL(csvBlob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${analysis.mission_id || 'marinescan'}_report.csv`;
          link.click();
          URL.revokeObjectURL(url);
        }
      } else if (selectedFile) {
        await downloadAnalysisReport(selectedFile, format, vessel);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Report export failed');
    } finally {
      setIsExporting(false);
    }
  };

  const formatTargetType = (target: AnalysisTarget) => target.class_name.replace('_', ' ').toUpperCase();

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

  const showSidePanel = imageSrc !== null;

  return (
    <div className={`${styles.container} sonar-page page-enter`}>
      <header className={styles.header}>
        <div className={styles.vesselInfo}>
          {/* Real, editable survey position — every detection is geolocated
              relative to this. Without it the backend falls back to a
              hardcoded point off Karachi, Pakistan, regardless of where the
              survey actually happened. */}
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            LAT
            <input
              type="number"
              step="0.0001"
              min={-90}
              max={90}
              value={vessel.vesselLat}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselLat");
                setVessel((v) => ({ ...v, vesselLat: clamped }));
              }}
              style={{ width: '72px', background: 'transparent', border: '1px solid currentColor', borderRadius: '3px', color: 'inherit', font: 'inherit', padding: '1px 4px' }}
            />
          </span>
          <span className={styles.divider}>|</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            LON
            <input
              type="number"
              step="0.0001"
              min={-180}
              max={180}
              value={vessel.vesselLon}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselLon");
                setVessel((v) => ({ ...v, vesselLon: clamped }));
              }}
              style={{ width: '76px', background: 'transparent', border: '1px solid currentColor', borderRadius: '3px', color: 'inherit', font: 'inherit', padding: '1px 4px' }}
            />
          </span>
          <span className={styles.divider}>|</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            HDG
            <input
              type="number"
              step="1"
              min={0}
              max={359}
              value={vessel.vesselHeadingDeg}
              disabled={isAnalyzing}
              onChange={(e) => {
                const raw = Number(e.target.value);
                const clamped = clampVesselField(raw, "vesselHeadingDeg");
                setVessel((v) => ({ ...v, vesselHeadingDeg: clamped }));
              }}
              style={{ width: '52px', background: 'transparent', border: '1px solid currentColor', borderRadius: '3px', color: 'inherit', font: 'inherit', padding: '1px 4px' }}
            />
          </span>
        </div>
        <div className={styles.statusBadges}>
          <span className={styles.statusDot}><i className={styles.dotGreen}></i> SONAR ONLINE</span>
          <span className={styles.statusDot}><i className={styles.dotGreen}></i> GPS FIX</span>
          <span className={styles.badgeDanger}>EDGE MODE</span>
        </div>
      </header>

      <div className={styles.scrollArea}>
        <div className={`${styles.mainContent} ${!showSidePanel ? styles.centered : ''}`}>
          <div className={`${styles.viewerPanel} ${isFullscreen ? styles.fullscreenMode : ''}`} ref={viewerPanelRef}>
            <div className={styles.viewerHeader}>
              <span>SONAR VIEWER</span>
              <div className={styles.viewerControls}>
                <button
                  type="button"
                  className={styles.iconBtn}
                  // onClick={handlePrevSample}
                  title="Previous sonar frame"
                  aria-label="Previous sonar frame"
                >
                  <ChevronLeft size={14} />
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  // onClick={handleNextSample}
                  title="Next sonar frame"
                  aria-label="Next sonar frame"
                >
                  <ChevronRight size={14} />
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={handleZoomIn}
                  aria-label="Zoom in"
                  title="Zoom in (+)"
                >
                  <ZoomIn size={14} />
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={handleZoomOut}
                  aria-label="Zoom out"
                  title="Zoom out (-)"
                >
                  <ZoomOut size={14} />
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  onClick={handleResetZoom}
                  aria-label="Fit to view"
                  title="Fit to view (100%)"
                >
                  <RotateCcw size={14} />
                </button>
                <button
                  type="button"
                  className={`${styles.iconBtn} ${isFullscreen ? styles.iconBtnActive : ''}`}
                  onClick={toggleFullscreen}
                  aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
                  title={isFullscreen ? 'Exit fullscreen (ESC)' : 'Enter fullscreen'}
                >
                  {isFullscreen ? <Minimize2 size={14} /> : <Maximize size={14} />}
                </button>
                <button
                  type="button"
                  className={`${styles.layerToggle} ${showLayers ? styles.layerToggleActive : ''}`}
                  onClick={() => setShowLayers((prev) => !prev)}
                  title="Toggle detection overlays"
                  aria-label="Toggle detection overlays"
                >
                  <Layers size={13} /> {showLayers ? 'ON' : 'OFF'}
                </button>
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
                    <div
                      className={styles.previewImage}
                      onClick={() => {
                        setImageSrc('/new.png');
                        setSampleIndex(0);
                      }}
                      style={{ cursor: 'pointer' }}
                      title="Click to open sample frame in Sonar Viewer"
                    >
                      <img src="/new.png" alt="AquaTrace sonar upload preview" />
                      <span>UPLOAD PREVIEW / RAW SONAR FIELD</span>
                      <i>click to inspect in viewer</i>
                    </div>
                    <div className={styles.previewNote}><strong>WHY THIS STEP MATTERS</strong><p>Raw sonar is noisy. AquaTrace removes speckle, preserves object outlines, and prepares the frame for detection and acoustic validation.</p></div>
                  </div>
                  <aside className={styles.emptyDetections}><div className={styles.emptyDetections__header}><strong>DETECTIONS</strong><span>TRK-042 · 5 found</span></div>{['Entangled Net', 'Steel Pipe', 'Cylinder', 'Entangled Net', 'Shipwreck'].map((name, index) => <div className={styles.emptyDetection} key={`${name}-${index}`}><i /><span><b>{name}</b><small>10.4823°N · {28 + index} m</small></span><strong>{[91, 76, 61, 84, 95][index]}%</strong></div>)}</aside>
                </div>
              ) : (
                <div
                  ref={viewportRef}
                  className={`${styles.sonarViewport} ${zoom > 1.0 ? styles.canPan : ''} ${isDragging ? styles.isDragging : ''}`}
                  onMouseDown={handleMouseDown}
                  onDoubleClick={handleDoubleClick}
                >
                  <div
                    className={`${styles.transformLayer} ${isAnimating ? styles.animating : ''}`}
                    style={{
                      width: baseSize.width > 0 ? `${baseSize.width}px` : '100%',
                      height: baseSize.height > 0 ? `${baseSize.height}px` : '100%',
                      transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${zoom})`,
                    }}
                  >
                    <img
                      ref={imageRef}
                      src={displayImage ?? imageSrc}
                      alt="Sonar Scan"
                      className={styles.sonarImage}
                      onLoad={handleImageLoad}
                      draggable={false}
                    />

                    {/* Vector Overlay Layer Synchronized with Image */}
                    {showLayers && (
                      <svg
                        className={styles.overlaySvg}
                        viewBox={`0 0 ${naturalSize.width || 800} ${naturalSize.height || 600}`}
                        preserveAspectRatio="none"
                      >
                        <defs>
                          <marker
                            id="arrow-yellow"
                            viewBox="0 0 10 10"
                            refX="8"
                            refY="5"
                            markerWidth="6"
                            markerHeight="6"
                            orient="auto-start-reverse"
                          >
                            <path d="M 0 1 L 10 5 L 0 9 z" fill="#facc15" />
                          </marker>
                          <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="3" result="blur" />
                            <feComposite in="SourceGraphic" in2="blur" operator="over" />
                          </filter>
                        </defs>

                        {displayTargets.map((target, idx) => {
                          const natW = naturalSize.width || 800;
                          const natH = naturalSize.height || 600;

                          let x = target.bbox.x_min ?? (target.bbox.normalized_x_min != null ? target.bbox.normalized_x_min * natW : 120);
                          let y = target.bbox.y_min ?? (target.bbox.normalized_y_min != null ? target.bbox.normalized_y_min * natH : 120);
                          let w = target.bbox.width || ((target.bbox.x_max ?? 0) - x) || ((target.bbox.normalized_x_max ?? 0.25) * natW - x) || 140;
                          let h = target.bbox.height || ((target.bbox.y_max ?? 0) - y) || ((target.bbox.normalized_y_max ?? 0.25) * natH - y) || 90;

                          if (x < 1 && y < 1 && w <= 1 && h <= 1) {
                            x = x * natW;
                            y = y * natH;
                            w = w * natW;
                            h = h * natH;
                          }

                          const isSelected = (selectedTargetId ?? displayTargets[0]?.detection_id) === target.detection_id;
                          const confPercent = Math.round((target.calibrated_confidence ?? 0.9) * 100);
                          const cornerLen = Math.min(18, Math.min(w, h) / 3);

                          const cx = x + w / 2;
                          const cy = y + h / 2;
                          const arrowEndX = cx + Math.min(65, w * 0.55);
                          const arrowEndY = cy + Math.min(55, h * 0.45);

                          return (
                            <g
                              key={target.detection_id || idx}
                              className={styles.targetOverlayGroup}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedTargetId(target.detection_id);
                              }}
                              style={{ cursor: 'pointer', pointerEvents: 'all' }}
                            >
                              {/* Cyan bounding box */}
                              <rect
                                x={x}
                                y={y}
                                width={w}
                                height={h}
                                rx="3"
                                stroke="#06b6d4"
                                strokeWidth={isSelected ? 3 : 2}
                                fill={isSelected ? 'rgba(6, 182, 212, 0.22)' : 'rgba(6, 182, 212, 0.08)'}
                                filter={isSelected ? 'url(#glow-cyan)' : undefined}
                              />

                              {/* Cyan corner HUD brackets */}
                              <path
                                d={`M ${x} ${y + cornerLen} L ${x} ${y} L ${x + cornerLen} ${y}
                                    M ${x + w - cornerLen} ${y} L ${x + w} ${y} L ${x + w} ${y + cornerLen}
                                    M ${x + w} ${y + h - cornerLen} L ${x + w} ${y + h} L ${x + w - cornerLen} ${y + h}
                                    M ${x + cornerLen} ${y + h} L ${x} ${y + h} L ${x} ${y + h - cornerLen}`}
                                stroke="#22d3ee"
                                strokeWidth={isSelected ? 3.5 : 2.5}
                                fill="none"
                              />

                              {/* Yellow acoustic shadow vector arrow */}
                              {target.shadow_evidence?.has_shadow && (
                                <g>
                                  <line
                                    x1={cx}
                                    y1={cy}
                                    x2={arrowEndX}
                                    y2={arrowEndY}
                                    stroke="#facc15"
                                    strokeWidth="2"
                                    strokeDasharray="4 3"
                                    markerEnd="url(#arrow-yellow)"
                                  />
                                  <text
                                    x={arrowEndX + 6}
                                    y={arrowEndY + 4}
                                    fill="#facc15"
                                    fontSize="10"
                                    fontFamily="monospace"
                                    fontWeight="bold"
                                  >
                                    SHADOW {Math.round(target.shadow_evidence.shadow_score * 100)}%
                                  </text>
                                </g>
                              )}

                              {/* Red target label badge */}
                              <g transform={`translate(${x}, ${Math.max(18, y - 22)})`}>
                                <rect
                                  x="0"
                                  y="0"
                                  width={Math.max(110, (target.display_name.length + 8) * 8)}
                                  height="19"
                                  rx="3"
                                  fill="#ef4444"
                                />
                                <text
                                  x="6"
                                  y="13.5"
                                  fill="#ffffff"
                                  fontSize="10.5"
                                  fontWeight="bold"
                                  fontFamily="system-ui, sans-serif"
                                  letterSpacing="0.5px"
                                >
                                  #{String(idx + 1).padStart(2, '0')} {target.display_name.toUpperCase()} {confPercent}%
                                </text>
                              </g>

                              {/* Target coordinates pill */}
                              <g transform={`translate(${x}, ${y + h + 4})`}>
                                <rect
                                  x="0"
                                  y="0"
                                  width="132"
                                  height="16"
                                  rx="3"
                                  fill="rgba(3, 7, 18, 0.85)"
                                  stroke="rgba(6, 182, 212, 0.4)"
                                  strokeWidth="1"
                                />
                                <text
                                  x="6"
                                  y="11.5"
                                  fill="#38bdf8"
                                  fontSize="9.5"
                                  fontFamily="monospace"
                                  fontWeight="600"
                                >
                                  {target.coordinates?.latitude?.toFixed(4) ?? '10.4823'}°N, {target.coordinates?.longitude?.toFixed(4) ?? '80.2144'}°E
                                </text>
                              </g>
                            </g>
                          );
                        })}
                      </svg>
                    )}
                  </div>

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
                      <span>LAT <strong>{displayTargets[0]?.coordinates.latitude.toFixed(5) ?? '10.48234'}</strong></span>
                      <span>LON <strong>{displayTargets[0]?.coordinates.longitude.toFixed(5) ?? '80.21452'}</strong></span>
                      <span>QUALITY <strong>{analysis?.quality_assessment.quality_tier ?? 'OPTIMAL'}</strong></span>
                      <span>CONF <strong>{displayTargets[0] ? `${Math.round((displayTargets[0].calibrated_confidence ?? 0.9) * 100)}%` : '94%'}</strong></span>
                    </div>
                    <div className={styles.metaRight}>
                      <div><span>ZOOM</span><strong>{Math.round(zoom * 100)}%</strong></div>
                      <div><span>FRM</span><strong>{String(sampleIndex + 1).padStart(4, '0')}</strong></div>
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
                  <span className={styles.headerTitle}>
                    <Radar size={13} /> DETECTION LIST
                  </span>
                  {hasTargets && (
                    <span className={styles.countBadge}>
                      {filteredTargets.length === displayTargets.length
                        ? `${displayTargets.length} Targets`
                        : `${filteredTargets.length} / ${displayTargets.length}`}
                    </span>
                  )}
                </div>

                <div className={styles.panelBlockBody}>
                  {isAnalyzing || !hasTargets ? (
                    <>
                      <div className={styles.skeletonRow}></div>
                      <div className={styles.skeletonRow}></div>
                    </>
                  ) : (
                    <>
                      {/* Symmetrical 50/50 Export Actions Bar */}
                      <div className={styles.exportActionsBar}>
                        <button
                          type="button"
                          className={`${styles.exportBtn} ${styles.exportBtnJson}`}
                          onClick={() => handleExport('json')}
                          disabled={isExporting}
                          title="Export full hydrographic report as JSON"
                        >
                          <FileJson size={13} />
                          <span>EXPORT JSON</span>
                        </button>
                        <button
                          type="button"
                          className={`${styles.exportBtn} ${styles.exportBtnCsv}`}
                          onClick={() => handleExport('csv')}
                          disabled={isExporting}
                          title="Export targets tabular report as CSV"
                        >
                          <FileSpreadsheet size={13} />
                          <span>EXPORT CSV</span>
                        </button>
                      </div>

                      {/* Filter Row */}
                      <div className={styles.filterRow}>
                        <button
                          type="button"
                          className={`${styles.filterChip} ${filter === 'all' ? styles.filterChipActive : ''}`}
                          onClick={() => setFilter('all')}
                        >
                          ALL ({displayTargets.length})
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

                      {/* Detection Cards List */}
                      <div className={styles.targetCardsList}>
                        {filteredTargets.map((target) => {
                          const originalIndex = displayTargets.findIndex((t) => t.detection_id === target.detection_id);
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
                                    {target.coordinates.latitude.toFixed(3)}°, {target.coordinates.longitude.toFixed(3)}°
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
                                  {target.risk_tier} RISK ({target.risk_score})
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

                        {filteredTargets.length === 0 && displayTargets.length > 0 && (
                          <div className={styles.emptyFilteredState}>
                            <p>No targets match the active filter.</p>
                            <button
                              type="button"
                              className={styles.resetFilterBtn}
                              onClick={() => setFilter('all')}
                            >
                              Show All Targets
                            </button>
                          </div>
                        )}

                        {displayTargets.length === 0 && (
                          <div className={styles.noTargetsState}>
                            <p>No acoustic anomalies or debris detected in this scan.</p>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}>
                  <span>ACOUSTIC VALIDATION</span>
                  {activeTarget && (
                    <span className={styles.countBadge}>
                      Target #{displayTargets.findIndex((t) => t.detection_id === activeTarget.detection_id) + 1}
                    </span>
                  )}
                </div>
                <div className={styles.panelBlockBody}>
                  {isAnalyzing || !hasTargets ? (
                    <div className={styles.skeletonRow}></div>
                  ) : (
                    <>
                      <div className={styles.metricRow}>
                        <span>Selected Target</span>
                        <strong>{activeTarget ? `${formatTargetType(activeTarget)} (${activeTarget.display_name})` : '—'}</strong>
                      </div>
                      <div className={styles.metricRow}>
                        <span>Shadow Length</span>
                        <strong>{activeTarget?.shadow_evidence.shadow_length_m?.toFixed(2) ?? '—'}m</strong>
                      </div>
                      <div className={styles.metricRow}>
                        <span>Est. Height</span>
                        <strong>{activeTarget?.shadow_evidence.estimated_height_m?.toFixed(2) ?? '—'}m</strong>
                      </div>
                      <div className={styles.metricRow}>
                        <span>Shadow Score</span>
                        <strong className={styles.greenText}>
                          {activeTarget ? `${Math.round(activeTarget.shadow_evidence.shadow_score * 100)}%` : '—'}
                        </strong>
                      </div>
                    </>
                  )}
                </div>
              </div>

              <div className={styles.panelBlock}>
                <div className={styles.panelBlockHeader}><span>SURVEY INTEL</span></div>
                <div className={styles.panelBlockBody}>
                  {isAnalyzing || !hasTargets ? (
                    <div className={styles.skeletonRow}></div>
                  ) : (
                    <div className={styles.grid2x2}>
                      <div><small>MISSION</small><h4>{analysis?.mission_id || 'AUV-TRK-042'}</h4></div>
                      <div><small>TARGETS</small><h4>{displayTargets.length}</h4></div>
                      <div><small>VERIFIED</small><h4>{verifiedCount}</h4></div>
                      <div><small>QUALITY</small><h4>{Math.round((analysis?.quality_assessment.overall_quality_score ?? 0.94) * 100)}%</h4></div>
                    </div>
                  )}
                </div>
              </div>

              {hasTargets && (
                <div className={styles.panelBlock}>
                  <div className={styles.panelBlockHeader}><span>TARGET CLASSIFICATION</span></div>
                  <div className={styles.panelBlockBody}>
                    <p className={styles.classificationSubtitle}>
                      {displayTargets.length} TARGETS DETECTED · {verifiedCount} VERIFIED
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
                        {displayTargets.map((target) => (
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

              {hasTargets && (
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