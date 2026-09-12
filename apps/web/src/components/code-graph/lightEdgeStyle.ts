/**
 * @file lightEdgeStyle
 * @description Edge visual weight curves: end/midpoint alpha, width profile,
 * distance zoom fade, and hub degree falloff.
 *
 * Responsibilities:
 * - Provide edge alpha and width profiles that thin toward the midpoint
 * - Fade edges as the camera zooms out and attenuate high-degree hub edges
 */

/** Light-theme edge visual weight: solid ends, lighter midpoint, gap = 1 - 0.618. */
export const LIGHT_EDGE_END_FACTOR = 1;
export const LIGHT_EDGE_MID_FACTOR = 0.618;

/** Alpha along an edge: 1 at the ends, 0.618 at the midpoint (always 1 for selected related edges). */
export function lightEdgeAlphaAt(t: number, solid: boolean): number {
  if (solid) return 1;
  const s = Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
  return LIGHT_EDGE_END_FACTOR - (LIGHT_EDGE_END_FACTOR - LIGHT_EDGE_MID_FACTOR) * s;
}

/** Line width: thickest near the nodes, thinnest at the midpoint, difference <= 30%. */
export const LIGHT_EDGE_WIDTH_END = 1;
export const LIGHT_EDGE_WIDTH_MID = 0.7;

export function lightEdgeWidthAt(t: number): number {
  const s = Math.sin(Math.PI * Math.min(1, Math.max(0, t)));
  return LIGHT_EDGE_WIDTH_END - (LIGHT_EDGE_WIDTH_END - LIGHT_EDGE_WIDTH_MID) * s;
}

/** Dim edges overall as the camera pulls away, reducing dark clumps in dense regions. */
export function computeLightEdgeZoomFade(cameraDistance: number): number {
  if (!Number.isFinite(cameraDistance) || cameraDistance <= 0) return 1;
  if (cameraDistance <= 320) return 1;
  if (cameraDistance >= 1200) return 0.28;
  const t = (cameraDistance - 320) / (1200 - 320);
  const s = t * t * (3 - 2 * t);
  return 1 - s * 0.72;
}

/** Degree falloff for hub nodes; the larger zoomedOutBoost (farther away), the stronger the falloff. */
export function computeLightEdgeDegreeFactor(degree: number, zoomedOutBoost = 0): number {
  const d = Math.max(0, degree);
  const k = 0.3 + zoomedOutBoost * 0.45;
  return 1 / (1 + Math.log2(1 + d) * k);
}
