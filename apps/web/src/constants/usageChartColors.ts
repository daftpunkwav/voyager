/**
 * @file usageChartColors
 * @description Chart palette anchored on the theme brand family (iOS system
 * hues, shared with the design tokens) so the charts, heatmap and legend read
 * as one instrument panel. The hues are dual-theme safe: vivid enough on dark
 * glass, not neon on the light surface.
 */

/** Multi-series palette (per-model donut / stacked bars): brand blue first,
 *  then semantic-adjacent hues ordered to keep neighbors distinguishable. */
export const USAGE_CHART_COLORS = [
  '#0a84ff',
  '#34c759',
  '#ff9f0a',
  '#af52de',
  '#64d2ff',
  '#ff375f',
  '#5e5ce6',
  '#8e8e93',
] as const;

/** Cached / uncached / completion split: semantic trio shared with the app's
 *  success / brand / warning accents. */
export const USAGE_TOKEN_COLORS = {
  cached: '#34c759',
  uncached: '#0a84ff',
  completion: '#ff9f0a',
} as const;
