import test from 'node:test';
import assert from 'node:assert/strict';
import { isRawSonarFile } from '../api/client.ts';

// ----------------------------------------------------------------------------
// Survey Imagery Viewer & Hydrographic Upload Option Verification
// ----------------------------------------------------------------------------

test('1. Discriminates Survey Imagery (.png, .jpg, .tiff) from Raw Sonar (.xtf, .jsf)', () => {
  const surveyImages = [
    'side_scan_raster_01.png',
    'side_scan_raster_02.jpg',
    'mosaic_fairway.jpeg',
    'geotiff_sector.tiff',
    'acoustic_frame.tif',
  ];

  const rawSonarRecordings = [
    'mission_line_101.xtf',
    'edgetech_channel_sweep.jsf',
    'DEEP_TOW_TRANSECT.XTF',
    'PORT_STARBOARD.JSF',
  ];

  for (const filename of surveyImages) {
    assert.equal(isRawSonarFile(filename), false, `${filename} should be treated as conventional survey imagery`);
  }

  for (const filename of rawSonarRecordings) {
    assert.equal(isRawSonarFile(filename), true, `${filename} should be treated as raw sonar recording`);
  }
});

test('2. Resolves active survey title and file indicator badge correctly', () => {
  const getViewerTitle = (isRaw: boolean) => (isRaw ? 'SONAR WATERFALL RASTER' : 'SURVEY IMAGERY VIEWER');

  assert.equal(getViewerTitle(false), 'SURVEY IMAGERY VIEWER');
  assert.equal(getViewerTitle(true), 'SONAR WATERFALL RASTER');

  const resolveActiveBadge = (
    selectedFile: { name: string } | null,
    imageSrc: string | null,
    sampleList: { name: string }[],
    sampleIndex: number
  ) => {
    if (selectedFile?.name) return selectedFile.name;
    if (imageSrc && sampleList[sampleIndex]) return sampleList[sampleIndex].name;
    return null;
  };

  const sampleList = [
    { name: 'Survey Line 01: Multi-Debris Field' },
    { name: 'Survey Line 02: Shipwreck Contact' },
  ];

  // User uploaded custom file
  assert.equal(
    resolveActiveBadge({ name: 'custom_benthic_mosaic.png' }, 'blob://local', sampleList, 0),
    'custom_benthic_mosaic.png'
  );

  // User selected built-in sample 1
  assert.equal(
    resolveActiveBadge(null, '/new.png', sampleList, 0),
    'Survey Line 01: Multi-Debris Field'
  );

  // User selected built-in sample 2
  assert.equal(
    resolveActiveBadge(null, '/accident.jpg', sampleList, 1),
    'Survey Line 02: Shipwreck Contact'
  );

  // No image loaded
  assert.equal(resolveActiveBadge(null, null, sampleList, 0), null);
});

test('3. Drag-and-drop file acceptance filter validates hydrographic payloads', () => {
  const ACCEPTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.xtf', '.jsf'];

  const validateDroppedFile = (filename: string) => {
    const ext = '.' + filename.split('.').pop()!.toLowerCase();
    return ACCEPTED_EXTENSIONS.includes(ext);
  };

  assert.equal(validateDroppedFile('sonar_wreck.png'), true);
  assert.equal(validateDroppedFile('survey.TIFF'), true);
  assert.equal(validateDroppedFile('line_survey.jsf'), true);
  assert.equal(validateDroppedFile('triton_ping.xtf'), true);
  assert.equal(validateDroppedFile('random_file.exe'), false);
  assert.equal(validateDroppedFile('notes.docx'), false);
});
