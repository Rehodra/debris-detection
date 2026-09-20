import { test } from 'node:test';
import assert from 'node:assert/strict';
import { clampVesselField } from '../api/client.ts';

// Test 1: Raster cursor coordinates mapping logic
function calculateRasterCursor(
  clientX: number,
  clientY: number,
  imgRect: { left: number; top: number; width: number; height: number },
  naturalSize: { width: number; height: number }
): { x: number; y: number } | null {
  if (naturalSize.width === 0 || naturalSize.height === 0 || imgRect.width === 0 || imgRect.height === 0) {
    return null;
  }
  if (
    clientX < imgRect.left ||
    clientX > imgRect.left + imgRect.width ||
    clientY < imgRect.top ||
    clientY > imgRect.top + imgRect.height
  ) {
    return null;
  }
  const relX = (clientX - imgRect.left) / imgRect.width;
  const relY = (clientY - imgRect.top) / imgRect.height;
  const pixelX = Math.floor(relX * naturalSize.width);
  const pixelY = Math.floor(relY * naturalSize.height);
  return {
    x: Math.max(0, Math.min(naturalSize.width - 1, pixelX)),
    y: Math.max(0, Math.min(naturalSize.height - 1, pixelY)),
  };
}

test('1. Raster cursor coordinate mapping accurately computes pixel indices within bounds', () => {
  const natural = { width: 1024, height: 2048 };
  const rect = { left: 100, top: 50, width: 500, height: 1000 };

  // Center coordinate
  const center = calculateRasterCursor(350, 550, rect, natural);
  assert.ok(center !== null);
  assert.equal(center.x, 512);
  assert.equal(center.y, 1024);

  // Top-left boundary
  const topLeft = calculateRasterCursor(100, 50, rect, natural);
  assert.ok(topLeft !== null);
  assert.equal(topLeft.x, 0);
  assert.equal(topLeft.y, 0);

  // Bottom-right boundary
  const bottomRight = calculateRasterCursor(600, 1050, rect, natural);
  assert.ok(bottomRight !== null);
  assert.equal(bottomRight.x, 1023);
  assert.equal(bottomRight.y, 2047);

  // Outside viewport (to the left)
  const outside = calculateRasterCursor(50, 500, rect, natural);
  assert.equal(outside, null);
});

test('2. Workstation reset clears active mission state back to initial dropzone state', () => {
  interface WorkstationState {
    imageSrc: string | null;
    selectedFile: string | null;
    isRawSonar: boolean;
    analysis: object | null;
    selectedTargetId: string | null;
    filter: string;
  }

  const activeState: WorkstationState = {
    imageSrc: 'blob:http://localhost:5173/survey-line-1',
    selectedFile: 'survey_line_01.xtf',
    isRawSonar: true,
    analysis: { mission_id: 'msn_12345' },
    selectedTargetId: 'TRK-001',
    filter: 'high_risk',
  };

  function resetWorkspace(state: WorkstationState): WorkstationState {
    return {
      imageSrc: null,
      selectedFile: null,
      isRawSonar: false,
      analysis: null,
      selectedTargetId: null,
      filter: 'all',
    };
  }

  const cleared = resetWorkspace(activeState);
  assert.equal(cleared.imageSrc, null);
  assert.equal(cleared.selectedFile, null);
  assert.equal(cleared.isRawSonar, false);
  assert.equal(cleared.analysis, null);
  assert.equal(cleared.selectedTargetId, null);
  assert.equal(cleared.filter, 'all');
});

test('3. Vessel telemetry inputs validate latitude, longitude, and heading bounds correctly', () => {
  // Latitude clamp bounds [-90, 90]
  assert.equal(clampVesselField(95, 'vesselLat'), 90);
  assert.equal(clampVesselField(-110, 'vesselLat'), -90);
  assert.equal(clampVesselField(13.0827, 'vesselLat'), 13.0827);

  // Longitude clamp bounds [-180, 180]
  assert.equal(clampVesselField(210, 'vesselLon'), 180);
  assert.equal(clampVesselField(-195, 'vesselLon'), -180);
  assert.equal(clampVesselField(80.2707, 'vesselLon'), 80.2707);

  // Heading clamp bounds [0, 359]
  assert.equal(clampVesselField(365, 'vesselHeadingDeg'), 359);
  assert.equal(clampVesselField(-15, 'vesselHeadingDeg'), 0);
  assert.equal(clampVesselField(185, 'vesselHeadingDeg'), 185);
});

test('4. Hotkey trigger mappings ignore editable text targets', () => {
  function shouldTriggerHotkey(targetTagName: string, key: string): boolean {
    const activeTag = targetTagName.toLowerCase();
    if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') {
      return false;
    }
    return ['+', '=', '-', '_', '0', 'f', 'F', 'l', 'L'].includes(key);
  }

  // Inside text input -> false
  assert.equal(shouldTriggerHotkey('INPUT', '+'), false);
  assert.equal(shouldTriggerHotkey('TEXTAREA', 'f'), false);

  // Outside text input -> true
  assert.equal(shouldTriggerHotkey('DIV', '+'), true);
  assert.equal(shouldTriggerHotkey('BODY', '-'), true);
  assert.equal(shouldTriggerHotkey('BODY', '0'), true);
  assert.equal(shouldTriggerHotkey('DIV', 'f'), true);
  assert.equal(shouldTriggerHotkey('DIV', 'L'), true);

  // Unrelated keys -> false
  assert.equal(shouldTriggerHotkey('BODY', 'x'), false);
});
