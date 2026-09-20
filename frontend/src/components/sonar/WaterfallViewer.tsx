import React, { useState, useRef, useEffect, useCallback, MouseEvent } from 'react';
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize,
  Minimize2,
  Layers,
  ScanLine,
  AlertCircle,
  ImageIcon,
  Compass,
  Upload,
  FolderOpen,
} from 'lucide-react';
import { MasterTargetResult, SonarRasterMetadata } from '../../api/client';
import styles from './WaterfallViewer.module.scss';

export interface SampleImageryOption {
  name: string;
  path: string;
  desc?: string;
}

export interface WaterfallViewerProps {
  imageSrc: string | null;
  isRawSonar?: boolean;
  isLoading?: boolean;
  error?: string | null;
  rasterMeta?: SonarRasterMetadata | null;
  targets: MasterTargetResult[];
  selectedTargetId: string | null;
  onSelectTarget: (id: string) => void;
  showLayers?: boolean;
  onToggleLayers?: () => void;
  onRetry?: () => void;
  onUploadFile?: (file: File) => void;
  activeFileName?: string | null;
  samples?: SampleImageryOption[];
  onSelectSample?: (index: number) => void;
  selectedSampleIndex?: number;
}

export const WaterfallViewer: React.FC<WaterfallViewerProps> = ({
  imageSrc,
  isRawSonar = false,
  isLoading = false,
  error = null,
  rasterMeta = null,
  targets,
  selectedTargetId,
  onSelectTarget,
  showLayers = true,
  onToggleLayers,
  onRetry,
  onUploadFile,
  activeFileName = null,
  samples = [],
  onSelectSample,
  selectedSampleIndex = -1,
}) => {
  const [zoom, setZoom] = useState<number>(1.0);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [baseSize, setBaseSize] = useState<{ width: number; height: number }>({ width: 0, height: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isAnimating, setIsAnimating] = useState<boolean>(false);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isDraggingOver, setIsDraggingOver] = useState<boolean>(false);
  const [showSampleMenu, setShowSampleMenu] = useState<boolean>(false);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);

  const viewerPanelRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const sampleMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: globalThis.MouseEvent) => {
      if (sampleMenuRef.current && !sampleMenuRef.current.contains(event.target as Node)) {
        setShowSampleMenu(false);
      }
    };
    if (showSampleMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showSampleMenu]);

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
    (testPanX: number, testPanY: number, targetZoom: number, baseW: number, baseH: number, vpW: number, vpH: number) => {
      if (baseW <= 0 || baseH <= 0 || vpW <= 0 || vpH <= 0) {
        return { x: 0, y: 0 };
      }
      const scaledW = baseW * targetZoom;
      const scaledH = baseH * targetZoom;

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
      if (scaledH > vpH) {
        minY = vpH - scaledH;
        maxY = 0;
      } else {
        minY = (vpH - scaledH) / 2;
        maxY = minY;
      }

      return {
        x: Math.min(maxX, Math.max(minX, testPanX)),
        y: Math.min(maxY, Math.max(minY, testPanY)),
      };
    },
    []
  );

  const updateBaseSize = useCallback(() => {
    if (!viewportRef.current || naturalSize.width === 0 || naturalSize.height === 0) return;
    const vpRect = viewportRef.current.getBoundingClientRect();
    if (vpRect.width === 0 || vpRect.height === 0) return;

    const imgAspect = naturalSize.width / naturalSize.height;
    const vpAspect = vpRect.width / vpRect.height;

    let w = vpRect.width;
    let h = vpRect.height;
    if (imgAspect > vpAspect) {
      h = w / imgAspect;
    } else {
      w = h * imgAspect;
    }

    setBaseSize({ width: w, height: h });
    setPan(clampPan(panRef.current.x, panRef.current.y, zoomRef.current, w, h, vpRect.width, vpRect.height));
  }, [naturalSize, clampPan]);

  useEffect(() => {
    updateBaseSize();
    window.addEventListener('resize', updateBaseSize);
    return () => window.removeEventListener('resize', updateBaseSize);
  }, [updateBaseSize]);

  const handleImageLoad = () => {
    if (imageRef.current) {
      setNaturalSize({
        width: imageRef.current.naturalWidth,
        height: imageRef.current.naturalHeight,
      });
    }
  };

  const handleResetZoom = useCallback(() => {
    setIsAnimating(true);
    setZoom(1.0);
    setPan({ x: 0, y: 0 });
    setTimeout(() => setIsAnimating(false), 200);
  }, []);

  const handleZoomIn = useCallback(() => {
    setZoom((prevZoom) => {
      const newZoom = Math.min(prevZoom * 1.25, 6.0);
      setIsAnimating(true);
      if (viewportRef.current) {
        const rect = viewportRef.current.getBoundingClientRect();
        setPan((prevPan) =>
          clampPan(prevPan.x, prevPan.y, newZoom, baseSizeRef.current.width, baseSizeRef.current.height, rect.width, rect.height)
        );
      }
      setTimeout(() => setIsAnimating(false), 200);
      return newZoom;
    });
  }, [clampPan]);

  const handleZoomOut = useCallback(() => {
    setZoom((prevZoom) => {
      const newZoom = Math.max(prevZoom / 1.25, 0.75);
      setIsAnimating(true);
      if (viewportRef.current) {
        const rect = viewportRef.current.getBoundingClientRect();
        setPan((prevPan) =>
          clampPan(prevPan.x, prevPan.y, newZoom, baseSizeRef.current.width, baseSizeRef.current.height, rect.width, rect.height)
        );
      }
      setTimeout(() => setIsAnimating(false), 200);
      return newZoom;
    });
  }, [clampPan]);

  const toggleFullscreen = useCallback(() => {
    if (!viewerPanelRef.current) return;
    if (!document.fullscreenElement) {
      if (viewerPanelRef.current.requestFullscreen) {
        viewerPanelRef.current.requestFullscreen().catch(() => {});
      }
      setIsFullscreen(true);
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen().catch(() => {});
      }
      setIsFullscreen(false);
    }
  }, []);

  // Hotkey navigation: + / - zoom, 0 fit, F fullscreen, L layer overlay
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
        return;
      }

      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        handleZoomIn();
      } else if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        handleZoomOut();
      } else if (e.key === '0') {
        e.preventDefault();
        handleResetZoom();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        toggleFullscreen();
      } else if (e.key === 'l' || e.key === 'L') {
        if (onToggleLayers) {
          e.preventDefault();
          onToggleLayers();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleZoomIn, handleZoomOut, handleResetZoom, toggleFullscreen, onToggleLayers]);

  const handleViewportMouseMove = (e: MouseEvent<HTMLDivElement>) => {
    if (!imageRef.current || naturalSize.width === 0 || naturalSize.height === 0) {
      setCursorPos(null);
      return;
    }
    const rect = imageRef.current.getBoundingClientRect();
    if (
      e.clientX >= rect.left &&
      e.clientX <= rect.right &&
      e.clientY >= rect.top &&
      e.clientY <= rect.bottom
    ) {
      const relX = (e.clientX - rect.left) / rect.width;
      const relY = (e.clientY - rect.top) / rect.height;
      const pixelX = Math.floor(relX * naturalSize.width);
      const pixelY = Math.floor(relY * naturalSize.height);
      setCursorPos({
        x: Math.max(0, Math.min(naturalSize.width - 1, pixelX)),
        y: Math.max(0, Math.min(naturalSize.height - 1, pixelY)),
      });
    } else {
      setCursorPos(null);
    }
  };

  const handleViewportMouseLeave = () => {
    setCursorPos(null);
  };

  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
      setTimeout(updateBaseSize, 100);
    };
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, [updateBaseSize]);

  const handleMouseDown = (e: MouseEvent<HTMLDivElement>) => {
    if (e.button !== 0 || zoom <= 1.0) return;
    isDraggingRef.current = true;
    setIsDragging(true);
    dragStartRef.current = {
      clientX: e.clientX,
      clientY: e.clientY,
      panX: pan.x,
      panY: pan.y,
    };

    const onMouseMove = (moveEvent: globalThis.MouseEvent) => {
      if (!isDraggingRef.current || !viewportRef.current) return;
      const dx = moveEvent.clientX - dragStartRef.current.clientX;
      const dy = moveEvent.clientY - dragStartRef.current.clientY;
      const testX = dragStartRef.current.panX + dx;
      const testY = dragStartRef.current.panY + dy;
      const vpRect = viewportRef.current.getBoundingClientRect();
      const clamped = clampPan(testX, testY, zoomRef.current, baseSizeRef.current.width, baseSizeRef.current.height, vpRect.width, vpRect.height);
      setPan(clamped);
    };

    const onMouseUp = () => {
      isDraggingRef.current = false;
      setIsDragging(false);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isDraggingOver) {
      setIsDraggingOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setIsDraggingOver(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);
    const files = e.dataTransfer.files;
    if (files && files.length > 0 && onUploadFile) {
      onUploadFile(files[0]);
    }
  };

  const natW = naturalSize.width || rasterMeta?.waterfall_width || 800;
  const natH = naturalSize.height || rasterMeta?.waterfall_height || 600;

  return (
    <div className={`${styles.viewerPanel} ${isFullscreen ? styles.fullscreenMode : ''}`} ref={viewerPanelRef}>
      {/* Header controls */}
      <div className={styles.viewerHeader}>
        <div className={styles.viewerTitle}>
          <Compass size={14} className={styles.compassIcon} />
          <span className={styles.titleText}>{isRawSonar ? 'SONAR WATERFALL RASTER' : 'SURVEY IMAGERY VIEWER'}</span>
          {activeFileName && (
            <span className={styles.activeFileBadge} title={`Active Survey: ${activeFileName}`}>
              {activeFileName}
            </span>
          )}
          {rasterMeta?.channel_layout && (
            <span className={styles.channelBadge}>{rasterMeta.channel_layout.toUpperCase()}</span>
          )}
        </div>
        <div className={styles.viewerControls}>
          {/* Integrated Upload / Import Button */}
          {onUploadFile && (
            <label
              className={styles.uploadToolbarBtn}
              title="Upload Survey Imagery (.PNG / .JPG / .TIFF) or Raw Sonar (.XTF / .JSF)"
            >
              <Upload size={13} />
              <span>IMPORT SURVEY</span>
              <input
                type="file"
                accept="image/*,.xtf,.jsf,.tif,.tiff"
                className={styles.hiddenFileInput}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onUploadFile(file);
                  e.target.value = '';
                }}
              />
            </label>
          )}

          {/* Sample Survey Frames Menu */}
          {samples && samples.length > 0 && onSelectSample && (
            <div className={styles.sampleSelectorWrap} ref={sampleMenuRef}>
              <button
                type="button"
                className={`${styles.sampleSelectBtn} ${showSampleMenu ? styles.sampleSelectBtnActive : ''}`}
                onClick={() => setShowSampleMenu((prev) => !prev)}
                title="Switch between sample survey imagery frames"
                aria-label="Sample survey imagery frames"
              >
                <FolderOpen size={13} />
                <span>SAMPLES</span>
              </button>
              {showSampleMenu && (
                <div className={styles.sampleDropdownMenu}>
                  <div className={styles.sampleMenuHeader}>SURVEY SAMPLE FRAMES</div>
                  {samples.map((s, idx) => (
                    <button
                      key={s.path}
                      type="button"
                      className={`${styles.sampleMenuItem} ${selectedSampleIndex === idx ? styles.sampleMenuItemActive : ''}`}
                      onClick={() => {
                        onSelectSample(idx);
                        setShowSampleMenu(false);
                      }}
                    >
                      <span className={styles.sampleMenuName}>{s.name}</span>
                      {s.desc && <span className={styles.sampleMenuDesc}>{s.desc}</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className={styles.controlDivider} />

          <button type="button" className={styles.iconBtn} onClick={handleZoomIn} aria-label="Zoom in" title="Zoom in (+)">
            <ZoomIn size={14} />
          </button>
          <button type="button" className={styles.iconBtn} onClick={handleZoomOut} aria-label="Zoom out" title="Zoom out (-)">
            <ZoomOut size={14} />
          </button>
          <button type="button" className={styles.iconBtn} onClick={handleResetZoom} aria-label="Fit to view" title="Fit to view (100%)">
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
          {onToggleLayers && (
            <button
              type="button"
              className={`${styles.layerToggle} ${showLayers ? styles.layerToggleActive : ''}`}
              onClick={onToggleLayers}
              title="Toggle detection overlays"
              aria-label="Toggle detection overlays"
            >
              <Layers size={13} /> {showLayers ? 'OVERLAY ON' : 'OVERLAY OFF'}
            </button>
          )}
        </div>
      </div>

      {/* Main Viewport with Drag-and-Drop support */}
      <div
        className={`${styles.viewportContainer} ${isDraggingOver ? styles.viewportDragOver : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drag-over overlay */}
        {isDraggingOver && (
          <div className={styles.dragOverOverlay}>
            <div className={styles.dragRadarRings}>
              <div className={styles.dragRadarRing} />
              <div className={styles.dragRadarRing} />
            </div>
            <Upload size={38} className={styles.dragIcon} />
            <h4>DROP SURVEY IMAGERY OR SONAR RECORDING</h4>
            <p>Release to immediately ingest and run hydrographic anomaly detection</p>
            <div className={styles.formatPills}>
              <span>.PNG</span>
              <span>.JPG</span>
              <span>.TIFF</span>
              <span>.XTF</span>
              <span>.JSF</span>
            </div>
          </div>
        )}

        {error ? (
          <div className={styles.stateOverlay}>
            <AlertCircle size={32} className={styles.errorIcon} />
            <h4>Unable to load sonar waterfall</h4>
            <p>{error}</p>
            {onRetry && (
              <button type="button" className={styles.retryButton} onClick={onRetry}>
                Retry Loading Raster
              </button>
            )}
          </div>
        ) : !imageSrc && !isLoading ? (
          <div className={styles.stateOverlay}>
            <div className={styles.emptyDropzoneCard}>
              <div className={styles.emptyIconPulse}>
                <Upload size={30} />
              </div>
              <h4>Survey Imagery & Sonar Viewer</h4>
              <p>
                Drop survey imagery (.png, .jpg, .tiff) or raw acoustic recording (.xtf, .jsf) directly into this viewer to begin.
              </p>

              <div className={styles.emptyActionsRow}>
                {onUploadFile && (
                  <label className={styles.emptyPrimaryUploadBtn}>
                    <Upload size={14} />
                    <span>Browse Survey Files</span>
                    <input
                      type="file"
                      accept="image/*,.xtf,.jsf,.tif,.tiff"
                      className={styles.hiddenFileInput}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) onUploadFile(file);
                        e.target.value = '';
                      }}
                    />
                  </label>
                )}
                {samples && samples.length > 0 && onSelectSample && (
                  <button
                    type="button"
                    className={styles.emptySampleBtn}
                    onClick={() => onSelectSample(0)}
                  >
                    <FolderOpen size={14} />
                    <span>Load Sample Scan</span>
                  </button>
                )}
              </div>

              <div className={styles.emptyFormatsRow}>
                <span>SUPPORTED:</span>
                <b>.PNG / .JPG / .TIFF (Imagery)</b>
                <i>•</i>
                <b>.XTF / .JSF (Raw Sonar)</b>
              </div>
            </div>
          </div>
        ) : (
          <div
            ref={viewportRef}
            className={`${styles.sonarViewport} ${zoom > 1.0 ? styles.canPan : ''} ${isDragging ? styles.isDragging : ''}`}
            onMouseDown={handleMouseDown}
            onMouseMove={handleViewportMouseMove}
            onMouseLeave={handleViewportMouseLeave}
          >
            {imageSrc && (
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
                  src={imageSrc}
                  alt="Sonar Waterfall Raster"
                  className={styles.sonarImage}
                  onLoad={handleImageLoad}
                  draggable={false}
                />

                {/* SVG Detection Overlays */}
                {showLayers && targets.length > 0 && (
                  <svg className={styles.overlaySvg} viewBox={`0 0 ${natW} ${natH}`} preserveAspectRatio="none">
                    <defs>
                      <marker id="arrow-yellow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 1 L 10 5 L 0 9 z" fill="#facc15" />
                      </marker>
                      <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feComposite in="SourceGraphic" in2="blur" operator="over" />
                      </filter>
                    </defs>

                    {targets.map((target, idx) => {
                      let x = target.bbox.x_min ?? (target.bbox.normalized_x_min != null ? target.bbox.normalized_x_min * natW : 120);
                      let y = target.bbox.y_min ?? (target.bbox.normalized_y_min != null ? target.bbox.normalized_y_min * natH : 120);
                      let w = target.bbox.width || ((target.bbox.x_max ?? 0) - x) || ((target.bbox.normalized_x_max ?? 0.25) * natW - x) || 120;
                      let h = target.bbox.height || ((target.bbox.y_max ?? 0) - y) || ((target.bbox.normalized_y_max ?? 0.25) * natH - y) || 80;

                      if (x < 1 && y < 1 && w <= 1 && h <= 1) {
                        x = x * natW;
                        y = y * natH;
                        w = w * natW;
                        h = h * natH;
                      }

                      const isSelected = selectedTargetId === target.detection_id;
                      const confPercent = Math.round((target.calibrated_confidence ?? target.ai_confidence ?? 0.9) * 100);
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
                            onSelectTarget(target.detection_id);
                          }}
                        >
                          {/* Bounding Box */}
                          <rect
                            x={x}
                            y={y}
                            width={w}
                            height={h}
                            rx="3"
                            stroke={isSelected ? '#00f0ff' : '#06b6d4'}
                            strokeWidth={isSelected ? 3 : 2}
                            fill={isSelected ? 'rgba(6, 182, 212, 0.25)' : 'rgba(6, 182, 212, 0.08)'}
                            filter={isSelected ? 'url(#glow-cyan)' : undefined}
                          />

                          {/* Corner HUD Brackets */}
                          <path
                            d={`M ${x} ${y + cornerLen} L ${x} ${y} L ${x + cornerLen} ${y}
                                M ${x + w - cornerLen} ${y} L ${x + w} ${y} L ${x + w} ${y + cornerLen}
                                M ${x + w} ${y + h - cornerLen} L ${x + w} ${y + h} L ${x + w - cornerLen} ${y + h}
                                M ${x + cornerLen} ${y + h} L ${x} ${y + h} L ${x} ${y + h - cornerLen}`}
                            stroke="#22d3ee"
                            strokeWidth={isSelected ? 3.5 : 2.5}
                            fill="none"
                          />

                          {/* Shadow vector if corroborated */}
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
                            </g>
                          )}

                          {/* Class / Label Badge */}
                          <g transform={`translate(${x}, ${Math.max(18, y - 22)})`}>
                            <rect
                              x="0"
                              y="0"
                              width={Math.max(100, (target.display_name.length + 8) * 7.5)}
                              height="19"
                              rx="3"
                              fill={target.risk_tier === 'CRITICAL' ? '#ef4444' : target.risk_tier === 'HIGH' ? '#ea580c' : '#0284c7'}
                            />
                            <text
                              x="6"
                              y="13.5"
                              fill="#ffffff"
                              fontSize="10"
                              fontWeight="bold"
                              fontFamily="system-ui, sans-serif"
                            >
                              #{String(idx + 1).padStart(2, '0')} {target.display_name.toUpperCase()} {confPercent}%
                            </text>
                          </g>
                        </g>
                      );
                    })}
                  </svg>
                )}
              </div>
            )}

            {/* Scanning / Loading state overlay */}
            {isLoading && (
              <div className={styles.scannerOverlay}>
                <div className={styles.scanLine} />
                <div className={styles.scanLabel}>
                  <ScanLine size={16} />
                  <span>DECODING PINGS & ASSEMBLING WATERFALL RASTER…</span>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Raster Metadata Footer */}
      <div className={styles.rasterMetaBar}>
        <div className={styles.metaCol}>
          <span className={styles.metaKey}>PINGS:</span>
          <strong className={styles.metaVal}>{rasterMeta?.total_pings ?? (naturalSize.height || '—')}</strong>
        </div>
        <div className={styles.metaCol}>
          <span className={styles.metaKey}>RASTER EXTENT:</span>
          <strong className={styles.metaVal}>
            {rasterMeta?.waterfall_width ?? naturalSize.width ?? '—'} × {rasterMeta?.waterfall_height ?? naturalSize.height ?? '—'} px
          </strong>
        </div>
        {rasterMeta?.nadir_pixel != null && (
          <div className={styles.metaCol}>
            <span className={styles.metaKey}>NADIR:</span>
            <strong className={styles.metaVal}>{Number(rasterMeta.nadir_pixel).toFixed(1)} px</strong>
          </div>
        )}
        {rasterMeta?.meters_per_pixel != null && (
          <div className={styles.metaCol}>
            <span className={styles.metaKey}>RESOLUTION:</span>
            <strong className={styles.metaVal}>{Number(rasterMeta.meters_per_pixel).toFixed(4)} m/px</strong>
          </div>
        )}
        {rasterMeta?.slant_range_m != null && (
          <div className={styles.metaCol}>
            <span className={styles.metaKey}>RANGE:</span>
            <strong className={styles.metaVal}>{Number(rasterMeta.slant_range_m).toFixed(1)} m</strong>
          </div>
        )}
        <div className={styles.metaCursor}>
          <span className={styles.metaKey}>CURSOR:</span>
          {cursorPos ? (
            <strong className={styles.metaVal}>
              X: {cursorPos.x} px, Y: {cursorPos.y} px
            </strong>
          ) : (
            <strong className={styles.metaValDim}>—</strong>
          )}
        </div>
        <div className={styles.metaZoom}>
          <span>ZOOM:</span>
          <strong>{Math.round(zoom * 100)}%</strong>
        </div>
      </div>
    </div>
  );
};

export default WaterfallViewer;
