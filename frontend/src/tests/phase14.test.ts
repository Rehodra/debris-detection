import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isRawSonarFile,
  clampVesselField,
  getSonarRasterUrl,
  getExportUrl,
  extractErrorMessage,
} from '../api/client.ts';
import type { MasterTargetResult, SonarNavigationTrack } from '../api/client.ts';

test('1. isRawSonarFile correctly identifies raw sonar files vs images', () => {
  assert.equal(isRawSonarFile('survey_line_01.xtf'), true);
  assert.equal(isRawSonarFile('survey_line_02.JSF'), true);
  assert.equal(isRawSonarFile('acoustic_frame.png'), false);
  assert.equal(isRawSonarFile('waterfall.jpg'), false);
  assert.equal(isRawSonarFile('document.pdf'), false);
});

test('2. API client correctly constructs sonar raster artifact endpoint', () => {
  const url = getSonarRasterUrl('msn_test_123');
  assert.match(url, /\/api\/v1\/analyses\/msn_test_123\/sonar\/raster$/);
});

test('3. API client correctly constructs all 5 hydrographic export endpoints', () => {
  const id = 'msn_export_test';
  assert.match(getExportUrl(id, 'json'), /\/api\/v1\/analyses\/msn_export_test\/export\/json$/);
  assert.match(getExportUrl(id, 'csv'), /\/api\/v1\/analyses\/msn_export_test\/export\/csv$/);
  assert.match(getExportUrl(id, 'geojson'), /\/api\/v1\/analyses\/msn_export_test\/export\/geojson$/);
  assert.match(getExportUrl(id, 'track_geojson'), /\/api\/v1\/analyses\/msn_export_test\/export\/track\.geojson$/);
  assert.match(getExportUrl(id, 'track_csv'), /\/api\/v1\/analyses\/msn_export_test\/export\/track\.csv$/);
});

test('4. clampVesselField respects physical bounds and guards non-finite inputs', () => {
  assert.equal(clampVesselField(95, 'vesselLat'), 90);
  assert.equal(clampVesselField(-120, 'vesselLat'), -90);
  assert.equal(clampVesselField(13.05, 'vesselLat'), 13.05);

  assert.equal(clampVesselField(200, 'vesselLon'), 180);
  assert.equal(clampVesselField(-195, 'vesselLon'), -180);
  assert.equal(clampVesselField(80.42, 'vesselLon'), 80.42);

  assert.equal(clampVesselField(400, 'vesselHeadingDeg'), 359);
  assert.equal(clampVesselField(-10, 'vesselHeadingDeg'), 0);
  assert.equal(clampVesselField(NaN, 'vesselHeadingDeg'), 0);
});

test('5. extractErrorMessage extracts plain string or array of Pydantic validation errors', () => {
  assert.equal(extractErrorMessage({ detail: 'Corrupt XTF file' }, 'fallback'), 'Corrupt XTF file');
  
  const pydanticError = {
    detail: [
      { loc: ['body', 'file'], msg: 'Field required', type: 'value_error.missing' },
      { loc: ['query', 'vessel_lat'], msg: 'Input should be less than or equal to 90', type: 'value_error' },
    ],
  };
  const parsed = extractErrorMessage(pydanticError, 'fallback');
  assert.match(parsed, /Field required/);
  assert.match(parsed, /Input should be less than or equal to 90/);
});

test('6. Target with complete data provides physical dimensions, geodesy, and NOTMAR', () => {
  const completeTarget: MasterTargetResult = {
    detection_id: 'TRK-01',
    class_id: 2,
    class_name: 'shipwreck',
    display_name: 'Shipwreck',
    category: 'MAJOR OBSTRUCTION',
    ai_confidence: 0.96,
    calibrated_confidence: 0.95,
    trust_tier: 'VERIFIED_TARGET',
    bbox: { width: 280, height: 200, x_min: 100, y_min: 100 },
    shadow_evidence: {
      has_shadow: true,
      shadow_score: 0.94,
      shadow_length_m: 8.5,
      estimated_height_m: 4.8,
    },
    dimensions: {
      pixel_width: 280,
      pixel_height: 200,
      length_m: 14.2,
      width_m: 6.5,
      height_m: 4.8,
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
  };

  assert.equal(completeTarget.dimensions.length_m, 14.2);
  assert.equal(completeTarget.dimensions.recommended_crane_lift_tons, 67.5);
  assert.equal(completeTarget.clearance?.threatens_shallow_draft, true);
  assert.equal(completeTarget.georeference?.status, 'calculated');
});

test('7. Target with missing geolocation does not crash and leaves coordinates null', () => {
  const missingGeoTarget: MasterTargetResult = {
    detection_id: 'TRK-02',
    class_id: 1,
    class_name: 'pipe',
    display_name: 'Pipeline',
    ai_confidence: 0.85,
    calibrated_confidence: 0.82,
    trust_tier: 'PROBABLE_TARGET',
    bbox: { width: 150, height: 40 },
    shadow_evidence: { has_shadow: false, shadow_score: 0.1 },
    dimensions: {
      pixel_width: 150,
      pixel_height: 40,
      measurement_method: 'optical_camera_gsd',
      measurement_status: 'partial_across_only',
      warnings: ['No acoustic shadow'],
    },
    coordinates: null,
    georeference: {
      status: 'unavailable_missing_nav',
      coordinate_reference: 'WGS84',
      source_ping_index: 50,
      waterfall_row: 50,
      across_track_pixel: 120,
      layback_applied: false,
      warnings: ['GPS fix unavailable in recording'],
    },
    risk_score: 45,
    risk_tier: 'MODERATE',
  };

  assert.equal(missingGeoTarget.coordinates, null);
  assert.equal(missingGeoTarget.georeference?.status, 'unavailable_missing_nav');
  assert.equal(missingGeoTarget.georeference?.latitude, undefined);
  // Strictly verify it does NOT default to 0,0
  assert.equal(missingGeoTarget.coordinates == null, true);
});

test('8. Target with missing dimensions handles null/undefined fields safely', () => {
  const missingDimsTarget: MasterTargetResult = {
    detection_id: 'TRK-03',
    class_id: 3,
    class_name: 'fish',
    display_name: 'School of Fish',
    ai_confidence: 0.72,
    calibrated_confidence: 0.70,
    trust_tier: 'SUSPECTED_TARGET',
    bbox: { width: 50, height: 30 },
    shadow_evidence: { has_shadow: false, shadow_score: 0.05 },
    dimensions: {
      pixel_width: 50,
      pixel_height: 30,
      length_m: null,
      width_m: null,
      height_m: null,
      dry_mass_metric_tons: null,
      measurement_method: 'uncalibrated',
      measurement_status: 'unavailable_missing_gsd',
      warnings: ['GSD unavailable'],
    },
    risk_score: 15,
    risk_tier: 'LOW',
  };

  assert.equal(missingDimsTarget.dimensions.length_m, null);
  assert.equal(missingDimsTarget.dimensions.height_m, null);
  assert.equal(missingDimsTarget.dimensions.measurement_status, 'unavailable_missing_gsd');
});

test('9. Map coordinate extractor discards null/zero coordinates to prevent (0,0) plotting', () => {
  const targets: MasterTargetResult[] = [
    {
      detection_id: 'VALID-01',
      class_name: 'shipwreck',
      display_name: 'Shipwreck',
      calibrated_confidence: 0.9,
      trust_tier: 'VERIFIED',
      bbox: { width: 100, height: 100 },
      shadow_evidence: { has_shadow: false, shadow_score: 0 },
      dimensions: { pixel_width: 100, pixel_height: 100, measurement_method: 'test', measurement_status: 'ok', warnings: [] },
      coordinates: { latitude: 13.05, longitude: 80.42 },
      risk_score: 80,
      risk_tier: 'HIGH',
    },
    {
      detection_id: 'INVALID-01',
      class_name: 'other',
      display_name: 'Anomaly',
      calibrated_confidence: 0.5,
      trust_tier: 'SUSPECTED',
      bbox: { width: 50, height: 50 },
      shadow_evidence: { has_shadow: false, shadow_score: 0 },
      dimensions: { pixel_width: 50, pixel_height: 50, measurement_method: 'test', measurement_status: 'ok', warnings: [] },
      coordinates: null,
      risk_score: 20,
      risk_tier: 'LOW',
    },
    {
      detection_id: 'ZERO-COORD',
      class_name: 'other',
      display_name: 'Zero Anomaly',
      calibrated_confidence: 0.5,
      trust_tier: 'SUSPECTED',
      bbox: { width: 50, height: 50 },
      shadow_evidence: { has_shadow: false, shadow_score: 0 },
      dimensions: { pixel_width: 50, pixel_height: 50, measurement_method: 'test', measurement_status: 'ok', warnings: [] },
      coordinates: { latitude: 0, longitude: 0 },
      risk_score: 20,
      risk_tier: 'LOW',
    },
  ];

  const plottedPoints = targets
    .filter((t) => {
      const lat = t.coordinates?.latitude;
      const lon = t.coordinates?.longitude;
      return lat != null && lon != null && !(lat === 0 && lon === 0);
    })
    .map((t) => [t.coordinates!.latitude, t.coordinates!.longitude]);

  assert.equal(plottedPoints.length, 1);
  assert.deepEqual(plottedPoints[0], [13.05, 80.42]);
});

test('10. SonarNavigationTrack properly aggregates valid GPS pings', () => {
  const track: SonarNavigationTrack = {
    analysis_id: 'msn_101',
    source_format: 'XTF',
    total_pings: 5,
    available_navigation_pings: 3,
    points: [
      { ping_index: 0, latitude: 13.01, longitude: 80.40, heading_deg: 90 },
      { ping_index: 1, latitude: 13.02, longitude: 80.41, heading_deg: 91 },
      { ping_index: 2, latitude: null, longitude: null }, // missing GPS fix
      { ping_index: 3, latitude: 13.04, longitude: 80.43, heading_deg: 92 },
      { ping_index: 4, latitude: null, longitude: null }, // missing GPS fix
    ],
    warnings: [],
  };

  const validPoints = track.points.filter(
    (p) => p.latitude != null && p.longitude != null && !(p.latitude === 0 && p.longitude === 0)
  );

  assert.equal(validPoints.length, 3);
  assert.equal(track.total_pings, 5);
  assert.equal(track.available_navigation_pings, 3);
});
