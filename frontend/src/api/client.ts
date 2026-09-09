const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

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
 * 0 for non-finite input (e.g. a cleared field). `min`/`max` on a number
 * input are advisory only — the browser still accepts typed values outside
 * that range, which the backend then rejects with a 400 — so this must run
 * on every change, not just be declared on the input.
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

export interface AnalysisTarget {
    detection_id: string;
    class_name: string;
    display_name: string;
    calibrated_confidence: number;
    trust_tier: string;
    bbox: {
        width: number;
        height: number;
        x_min?: number;
        y_min?: number;
        x_max?: number;
        y_max?: number;
        normalized_x_min?: number;
        normalized_y_min?: number;
        normalized_x_max?: number;
        normalized_y_max?: number;
    };
    shadow_evidence: {
        has_shadow: boolean;
        shadow_score: number;
        shadow_length_m?: number | null;
        estimated_height_m?: number | null;
    };
    dimensions: {
        length_m: number;
        width_m: number;
        height_m: number;
    };
    coordinates: {
        latitude: number;
        longitude: number;
    };
    risk_score: number;
    risk_tier: string;
}

export interface MasterAnalysisResult {
    mission_id: string;
    image_metadata: { width: number; height: number; format?: string | null };
    quality_assessment: { overall_quality_score: number; quality_tier: string };
    targets: AnalysisTarget[];
    summary: {
        total_targets_detected: number;
        verified_targets: number;
        probable_debris: number;
        ambiguous_anomalies: number;
        suspected_false_alarms: number;
        max_hazard_score: number;
        primary_alert_message: string;
    };
    geojson?: { type: 'FeatureCollection'; features: Array<{ type: 'Feature'; geometry: { type: 'Point'; coordinates: number[] }; properties: Record<string, unknown> }> } | null;
    prediction_image_url?: string | null;
    annotated_image_base64?: string | null;
}

export interface AnalysisHistoryItem {
    id: number;
    mission_id: string;
    created_at: string;
    total_targets: number;
    verified_targets: number;
    risk_tier: string;
    class_breakdown: Record<string, number>;
    vessel_lat?: number | null;
    vessel_lon?: number | null;
    vessel_heading?: number | null;
    filename?: string | null;
}

/**
 * FastAPI/Pydantic error responses don't always carry a plain string in
 * `detail` — validation errors (422/400) return an array of
 * { loc, msg, type } objects instead. Stringifying that array directly (the
 * previous behaviour, `body?.detail ?? fallback`) produced the literal text
 * "[object Object]" in the UI with no indication of what was actually wrong.
 */
function extractErrorMessage(body: unknown, fallback: string): string {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
            .join('; ') || fallback;
    }
    return fallback;
}

function vesselParamString(vessel?: VesselParams): string {
    if (!vessel) return '';
    return new URLSearchParams({
        vessel_lat: String(vessel.vesselLat),
        vessel_lon: String(vessel.vesselLon),
        vessel_heading_deg: String(vessel.vesselHeadingDeg),
    }).toString();
}

export async function analyzeSonarImage(file: File, vessel?: VesselParams): Promise<MasterAnalysisResult> {
    const formData = new FormData();
    formData.append('file', file);

    const query = vesselParamString(vessel);
    const url = query ? `${API_BASE_URL}/api/v1/analyses/analyze?${query}` : `${API_BASE_URL}/api/v1/analyses/analyze`;

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
    link.click();
    URL.revokeObjectURL(url);
}

export async function getAnalysisHistory(): Promise<AnalysisHistoryItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/v1/analyses/history`);
    if (!response.ok) return [];
    return response.json();
}
