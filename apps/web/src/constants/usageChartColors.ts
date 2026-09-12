/**
 * @file usageChartColors
 * @description Chart color palette tuned for the dark liquid-glass theme.
 */

/** Usage chart palette (dark liquid glass). */
export const USAGE_CHART_COLORS = [
  '#5b8def',
  '#3ecf8e',
  '#a78bfa',
  '#f87171',
  '#fb923c',
  '#22d3ee',
  '#f472b6',
  '#94a3b8',
] as const;

export const USAGE_TOKEN_COLORS = {
  cached: '#3ecf8e',
  uncached: '#5b8def',
  completion: '#fb923c',
} as const;
