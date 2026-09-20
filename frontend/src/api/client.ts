export const API_BASE_URL =
    (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_BASE_URL)
        ? (import.meta as any).env.VITE_API_BASE_URL
        : 'http://localhost:8000';

export interface VesselParams {
    vesselLat: number;
    vesselLon: number;
    vesselHeadingDeg: number;
}

/**
 * Physically valid bounds for each vessel field. A single source of truth so
 * Map.tsx and SonarAnalysis.tsx clamp the same way instead of each carrying
 * its own copy of these numbers.
 */
export const VESSEL_BOUNDS = {
    vesselLat: { min: -90, max: 90 },
    vesselLon: { min: -180, max: 180 },
    vesselHeadingDeg: { min: 0, max: 359 },
} as const;

/**
 * Clamp a raw input value into a vessel field's valid range, falling back to
 * 0 for non-finite input (e.g. a cleared field).
 */
export function clampVesselField(raw: number, field: keyof VesselParams): number {
    const { min, max } = VESSEL_BOUNDS[field];
    return Number.isFinite(raw) ? Math.min(max, Math.max(min, raw)) : 0;
}

export function resolveApiAssetUrl(assetUrl: string | null | undefined): string | null {
    if (!assetUrl) return null;
    if (assetUrl.startsWith('data:') || assetUrl.startsWith('blob:')) return assetUrl;
    return new URL(assetUrl, `${API_BASE_URL}/`).toString();
}

export function isRawSonarFile(fileNameOrFile: string | File): boolean {
    const name = typeof fileNameOrFile === 'string' ? fileNameOrFile : fileNameOrFile.name;
    const lower = name.toLowerCase();
    return lower.endsWith('.xtf') || lower.endsWith('.jsf');
}

// ============================================================================
// Sonar & Geospatial Types (strictly aligned with backend Pydantic schemas)
// ============================================================================

export type SonarFormat = 'XTF' | 'JSF' | 'UNKNOWN';

export interface SonarNavigation {
    timestamp?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    heading_deg?: number | null;
    altitude_m?: number | null;
    depth_m?: number | null;
    source?: string | null;
    heading?: number | null;
    altitude?: number | null;
    depth?: number | null;
}

export interface SonarPingTelemetry {
    ping_index: number;
    timestamp?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    heading_deg?: number | null;
    altitude_m?: number | null;
    depth_m?: number | null;
    source_format?: string | null;
    channel_id?: number | null;
    waterfall_row?: number | null;
    heading?: number | null;
    altitude?: number | null;
    depth?: number | null;
}

export interface SonarNavigationTrack {
    analysis_id?: string | null;
    source_format: string;
    total_pings: number;
    available_navigation_pings: number;
    points: SonarPingTelemetry[];
    warnings: string[];
}

export interface SonarChannelInfo {
    channel_id: number;
    channel_name: string;
    frequency_hz?: number | null;
    sample_count?: number | null;
    range_m?: number | null;
    sample_format?: string | null;
    available: boolean;
}

export interface SonarFileMetadata {
    filename: string;
    format: string;
    file_size_bytes: number;
    total_pings: number;
    channel_count: number;
    channels: SonarChannelInfo[];
    navigation_available: boolean;
    warnings: string[];
}

export interface SonarInspectResponse {
    filename: string;
    format: string;
    file_size_bytes: number;
    total_pings: number;
    channel_count: number;
    channels: SonarChannelInfo[];
    navigation_available: boolean;
    telemetry?: SonarNavigation | null;
    warnings: string[];
    errors: string[];
}

export interface SonarTargetGeoreference {
    status: string;
    coordinate_reference: string;
    latitude?: number | null;
    longitude?: number | null;
    source_ping_index: number;
    waterfall_row: number;
    across_track_pixel: number;
    across_track_offset_m?: number | null;
    slant_range_m?: number | null;
    heading_deg?: number | null;
    layback_applied: boolean;
    layback_distance_m?: number | null;
    vessel_latitude?: number | null;
    vessel_longitude?: number | null;
    sensor_latitude?: number | null;
    sensor_longitude?: number | null;
    warnings: string[];
}

export interface MasterPhysicalDimensions {
    pixel_width: number;
    pixel_height: number;
    across_track_m?: number | null;
    along_track_m?: number | null;
    slant_range_m?: number | null;
    ground_range_m?: number | null;
    length_m?: number | null;
    width_m?: number | null;
    height_m?: number | null;
    area_sq_m?: number | null;
    estimated_volume_m3?: number | null;
    dry_mass_metric_tons?: number | null;
    submerged_weight_kn?: number | null;
    recommended_crane_lift_tons?: number | null;
    seabed_stability_index?: number | null;
    seabed_mobility_status?: string | null;
    measurement_method: string;
    measurement_status: string;
    warnings: string[];
}

export type TargetDimensions = MasterPhysicalDimensions;

export interface NavigationalClearance {
    water_depth_m: number;
    object_height_m: number;
    clearance_m: number;
    threatens_shallow_draft: boolean;
    threatens_medium_draft: boolean;
    threatens_deep_draft: boolean;
}

export interface ActionRecommendation {
    category: string;
    priority: string;
    action_text: string;
    authority_standard: string;
}

export interface RiskFactors {
    navigational_risk: number;
    trawl_risk: number;
    infrastructure_risk: number;
    environmental_risk: number;
    mobility_risk: number;
}

export interface TargetRiskAssessment {
    detection_id: string;
    class_name: string;
    target_type: string;
    composite_risk_score: number;
    risk_tier: string;
    color_hex: string;
    clearance: NavigationalClearance;
    factors: RiskFactors;
    recommendations: ActionRecommendation[];
    geolocation_available: boolean;
    dimensions_available: boolean;
    notmar_required: boolean;
    notmar_status: string;
    notmar_reason?: string | null;
    warnings: string[];
}

export interface ShadowEvidence {
    has_shadow: boolean;
    shadow_score: number;
    cardinal_direction?: string;
    direction_degrees?: number;
    shadow_length_m?: number | null;
    estimated_height_m?: number | null;
}

export interface BoundingBox {
    x_min?: number;
    y_min?: number;
    x_max?: number;
    y_max?: number;
    width: number;
    height: number;
    normalized_x_min?: number;
    normalized_y_min?: number;
    normalized_x_max?: number;
    normalized_y_max?: number;
}

export interface AnalysisTarget {
    detection_id: string;
    class_name: string;
    display_name: string;
    calibrated_confidence: number;
    trust_tier: string;
    bbox: BoundingBox;
    shadow_evidence: ShadowEvidence;
    dimensions: MasterPhysicalDimensions;
    coordinates?: {
        latitude: number;
        longitude: number;
    } | null;
    risk_score: number;
    risk_tier: string;
    // Extended fields matching MasterTargetResult
    class_id?: number;
    category?: string;
    ai_confidence?: number;
    explainability_notes?: string[];
    distance_from_sensor_m?: number | null;
    bearing_degrees?: number | null;
    georeference?: SonarTargetGeoreference | null;
    color_hex?: string;
    clearance?: NavigationalClearance;
    action_recommendations?: ActionRecommendation[];
}

export type MasterTargetResult = AnalysisTarget;

export interface QualityAssessment {
    laplacian_sharpness?: number;
    rms_contrast?: number;
    snr_db?: number;
    underexposed_ratio?: number;
    overexposed_ratio?: number;
    overall_quality_score: number;
    quality_tier: string;
    is_usable_for_mission?: boolean;
    quality_notes?: string[];
}

export interface StageTimings {
    input_validation_ms?: number;
    quality_check_ms?: number;
    preprocessing_ms?: number;
    yolo_inference_ms?: number;
    candidate_extraction_ms?: number;
    shadow_evidence_ms?: number;
    physics_validation_ms?: number;
    confidence_fusion_ms?: number;
    geolocation_ms?: number;
    dimension_estimate_ms?: number;
    risk_classification_ms?: number;
    total_pipeline_ms: number;
}

export interface ExecutiveSummary {
    total_targets_detected: number;
    verified_targets: number;
    probable_debris: number;
    ambiguous_anomalies: number;
    suspected_false_alarms: number;
    class_breakdown?: Record<string, number>;
    risk_tier_breakdown?: Record<string, number>;
    immediate_notmar_required?: boolean;
    max_hazard_score: number;
    primary_alert_message: string;
}

export interface SonarMetadataContext {
    format: string;
    filename?: string | null;
    total_pings: number;
    channel_count: number;
    channels_included?: number[];
    waterfall_width: number;
    waterfall_height: number;
    channel_layout: string;
    nadir_pixel_x?: number | null;
    meters_per_pixel?: number | null;
    slant_range_m?: number | null;
    navigation?: SonarNavigation | null;
    warnings: string[];
    artifact_id?: string | null;
    raster_reference?: string | null;
    raster_path?: string | null;
    track_artifact_id?: string | null;
    track_reference?: string | null;
}

export interface AnalysisSourceInfo {
    filename?: string | null;
    format: string;
    file_size?: number | null;
    file_size_bytes?: number | null;
}

export interface SonarRasterMetadata {
    total_pings?: number | null;
    channel_count?: number | null;
    selected_channels?: number[];
    channel_layout?: string | null;
    waterfall_width?: number | null;
    waterfall_height?: number | null;
    nadir_pixel?: number | null;
    meters_per_pixel?: number | null;
    slant_range_m?: number | null;
    artifact_id?: string | null;
    raster_reference?: string | null;
    track_artifact_id?: string | null;
    track_reference?: string | null;
    coordinate_convention?: string;
}

export interface MasterAnalysisResult {
    status?: string;
    mission_id: string;
    image_metadata: { width: number; height: number; format?: string | null };
    quality_assessment: QualityAssessment;
    timings?: StageTimings;
    targets: MasterTargetResult[];
    summary: ExecutiveSummary;
    geojson?: {
        type: 'FeatureCollection';
        features: Array<{
            type: 'Feature';
            geometry: { type: 'Point'; coordinates: [number, number] };
            properties: Record<string, unknown>;
        }>;
    } | null;
    prediction_image_url?: string | null;
    prediction_image_path?: string | null;
    annotated_image_base64?: string | null;
    sonar_metadata?: SonarMetadataContext | null;
}

export interface SonarAnalysisResponse {
    status: string;
    source: AnalysisSourceInfo;
    sonar?: SonarRasterMetadata | null;
    navigation?: SonarNavigation | null;
    analysis: MasterAnalysisResult;
    warnings: string[];
    // Top-level backward compatibility fields:
    mission_id?: string | null;
    targets: MasterTargetResult[];
    summary?: ExecutiveSummary | null;
    timings?: StageTimings | null;
    geojson?: MasterAnalysisResult['geojson'];
    quality_assessment?: QualityAssessment | null;
    image_metadata?: MasterAnalysisResult['image_metadata'];
    sonar_metadata?: SonarMetadataContext | null;
}

export interface AnalysisHistoryItem {
    id?: number;
    mission_id: string;
    created_at: string;
    total_targets: number;
    verified_targets: number;
    risk_tier?: string | null;
    class_breakdown: Record<string, number>;
    vessel_lat?: number | null;
    vessel_lon?: number | null;
    vessel_heading?: number | null;
    filename?: string | null;
}

export type ExportFormat = 'json' | 'csv' | 'geojson' | 'track_geojson' | 'track_csv';

// ============================================================================
// API Client Methods
// ============================================================================

export function extractErrorMessage(body: unknown, fallback: string): string {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return (
            detail
                .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
                .join('; ') || fallback
        );
    }
    return fallback;
}

function buildVesselQuery(vessel?: VesselParams, extraParams?: Record<string, string | number | boolean | undefined>): string {
    const params = new URLSearchParams();
    if (vessel) {
        params.set('vessel_lat', String(vessel.vesselLat));
        params.set('vessel_lon', String(vessel.vesselLon));
        params.set('vessel_heading_deg', String(vessel.vesselHeadingDeg));
    }
    if (extraParams) {
        for (const [key, val] of Object.entries(extraParams)) {
            if (val !== undefined && val !== null) {
                params.set(key, String(val));
            }
        }
    }
    const str = params.toString();
    return str ? `?${str}` : '';
}

/**
 * Executes the master pipeline on conventional imagery (.png, .jpg, .tiff, etc.)
 */
export async function analyzeSonarImage(
    file: File,
    vessel?: VesselParams,
    options?: { water_depth_m?: number; meters_per_pixel?: number; confidence_threshold?: number }
): Promise<MasterAnalysisResult> {
    const formData = new FormData();
    formData.append('file', file);

    const query = buildVesselQuery(vessel, options);
    const url = `${API_BASE_URL}/api/v1/analyses/analyze${query}`;

    const response = await fetch(url, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(extractErrorMessage(body, `Analysis failed (${response.status})`));
    }

    return response.json() as Promise<MasterAnalysisResult>;
}

/**
 * Executes the master pipeline on raw sonar binaries (.xtf, .jsf).
 * Returns the unified SonarAnalysisResponse contract.
 */
export async function analyzeSonarFile(
    file: File,
    vessel?: VesselParams,
    options?: {
        max_pings?: number;
        channels?: string[];
        water_depth_m?: number;
        meters_per_pixel?: number;
        confidence_threshold?: number;
    }
): Promise<SonarAnalysisResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const extra: Record<string, string | number | boolean | undefined> = {};
    if (options?.max_pings) extra.max_pings = options.max_pings;
    if (options?.water_depth_m) extra.water_depth_m = options.water_depth_m;
    if (options?.meters_per_pixel) extra.meters_per_pixel = options.meters_per_pixel;
    if (options?.confidence_threshold) extra.confidence_threshold = options.confidence_threshold;
    if (options?.channels && options.channels.length > 0) extra.channels = options.channels.join(',');

    const query = buildVesselQuery(vessel, extra);
    const url = `${API_BASE_URL}/api/v1/analyses/sonar${query}`;

    const response = await fetch(url, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(extractErrorMessage(body, `Raw sonar analysis failed (${response.status})`));
    }

    return response.json() as Promise<SonarAnalysisResponse>;
}

/**
 * Returns the exact, stable URL to stream the generated waterfall raster artifact.
 */
export function getSonarRasterUrl(analysisId: string): string {
    return `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(analysisId)}/sonar/raster`;
}

/**
 * Retrieves the ordered ping navigation track for a completed sonar analysis.
 */
export async function getSonarTrack(analysisId: string): Promise<SonarNavigationTrack> {
    const url = `${API_BASE_URL}/api/v1/analyses/${encodeURIComponent(analysisId)}/sonar/track`;
    const response = await fetch(url);
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(extractErrorMessage(body, `Failed to load navigation track (${response.status})`));
    }
    return response.json() as Promise<SonarNavigationTrack>;
}

/**
 * Returns the backend URL for the specified hydrographic export.
 */
export function getExportUrl(analysisId: string, format: ExportFormat): string {
    const encodedId = encodeURIComponent(analysisId);
    switch (format) {
        case 'json':
            return `${API_BASE_URL}/api/v1/analyses/${encodedId}/export/json`;
        case 'csv':
            return `${API_BASE_URL}/api/v1/analyses/${encodedId}/export/csv`;
        case 'geojson':
            return `${API_BASE_URL}/api/v1/analyses/${encodedId}/export/geojson`;
        case 'track_geojson':
            return `${API_BASE_URL}/api/v1/analyses/${encodedId}/export/track.geojson`;
        case 'track_csv':
            return `${API_BASE_URL}/api/v1/analyses/${encodedId}/export/track.csv`;
    }
}

/**
 * Initiates direct browser download of a backend-generated hydrographic export artifact.
 */
export async function downloadExport(analysisId: string, format: ExportFormat): Promise<void> {
    const url = getExportUrl(analysisId, format);
    const response = await fetch(url);

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(extractErrorMessage(body, `Export download failed (${response.status})`));
    }

    // Extract filename from Content-Disposition header if available
    const disposition = response.headers.get('Content-Disposition');
    let filename = `marinescan_${analysisId}_${format}`;
    if (disposition) {
        const match = disposition.match(/filename="?([^";]+)"?/);
        if (match?.[1]) {
            filename = match[1];
        }
    } else {
        const extMap: Record<ExportFormat, string> = {
            json: 'json',
            csv: 'csv',
            geojson: 'geojson',
            track_geojson: 'track.geojson',
            track_csv: 'track.csv',
        };
        filename = `marinescan_${analysisId}.${extMap[format]}`;
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(objectUrl);
}

/**
 * Legacy download handler for raw file report export.
 */
export async function downloadAnalysisReport(file: File, format: 'json' | 'csv', vessel?: VesselParams): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);

    const queryParams = new URLSearchParams({ report_format: format });
    if (vessel) {
        queryParams.set('vessel_lat', String(vessel.vesselLat));
        queryParams.set('vessel_lon', String(vessel.vesselLon));
        queryParams.set('vessel_heading_deg', String(vessel.vesselHeadingDeg));
    }

    const response = await fetch(`${API_BASE_URL}/api/v1/exports/report?${queryParams.toString()}`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(extractErrorMessage(body, `Report export failed (${response.status})`));
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `marinescan-report.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

export async function getAnalysisHistory(): Promise<AnalysisHistoryItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/v1/analyses/history`);
    if (!response.ok) return [];
    return response.json();
}
