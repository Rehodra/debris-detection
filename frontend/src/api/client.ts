const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

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
    bbox: { width: number; height: number };
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
    prediction_image_url?: string | null;
    annotated_image_base64?: string | null;
}

export async function analyzeSonarImage(file: File): Promise<MasterAnalysisResult> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/v1/analyses/analyze`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Analysis failed (${response.status})`);
    }

    return response.json() as Promise<MasterAnalysisResult>;
}

export async function downloadAnalysisReport(file: File, format: 'json' | 'csv'): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE_URL}/api/v1/exports/report?report_format=${format}`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Report export failed (${response.status})`);
    }

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `marinescan-report.${format}`;
    link.click();
    URL.revokeObjectURL(url);
}
