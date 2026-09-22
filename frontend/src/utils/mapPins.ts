import L from 'leaflet';

/**
 * Generates an SVG-based map pin DivIcon for detected debris and sonar targets.
 * Instead of simple circular dots ("points"), this renders an iconic, high-resolution
 * teardrop location pin with a target sequence number, white border, and elevation shadow.
 */
export function createTargetPinIcon(
  color: string,
  isSelected: boolean = false,
  index?: number | string
): L.DivIcon {
  const width = isSelected ? 32 : 26;
  const height = isSelected ? 42 : 34;
  const numStr = index != null ? String(index) : '';
  const isMultiDigit = numStr.length > 1;

  // Teardrop pin path anchored with tip at bottom center (14, 35.5) in 28x36 space
  const pathD = 'M 14,35.5 C 14,35.5 2,21 2,14 A 12,12 0 1 1 26,14 C 26,21 14,35.5 14,35.5 Z';
  const filterStyle = isSelected
    ? 'filter: drop-shadow(0 0 8px rgba(2, 132, 199, 0.9)) drop-shadow(0 4px 6px rgba(0,0,0,0.45));'
    : 'filter: drop-shadow(0 3px 5px rgba(0,0,0,0.35));';

  const innerSvg = numStr
    ? `<circle cx="14" cy="14" r="7.5" fill="#ffffff" />
       <text x="14" y="${isMultiDigit ? '16.8' : '17.2'}" text-anchor="middle" fill="${color}" font-size="${isMultiDigit ? '7.5' : '9'}" font-weight="800" font-family="'Poppins', system-ui, sans-serif">${numStr}</text>`
    : `<circle cx="14" cy="14" r="6.2" fill="#ffffff" />
       <circle cx="14" cy="14" r="3.2" fill="${color}" />`;

  const html = `
    <div style="width: ${width}px; height: ${height}px; display: flex; align-items: center; justify-content: center; cursor: pointer; ${filterStyle} transform: ${isSelected ? 'scale(1.12)' : 'scale(1)'}; transition: transform 0.18s ease;">
      <svg width="${width}" height="${height}" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="${pathD}" fill="${color}" stroke="#ffffff" stroke-width="${isSelected ? '2.5' : '1.5'}" stroke-linejoin="round"/>
        ${innerSvg}
      </svg>
    </div>
  `;

  return L.divIcon({
    className: 'sonar-map-pin',
    html,
    iconSize: [width, height],
    iconAnchor: [width / 2, height],
    popupAnchor: [0, -height - 2],
  });
}
