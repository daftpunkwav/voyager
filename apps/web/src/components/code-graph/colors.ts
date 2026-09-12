/**
 * @file colors
 * @description Node type and status color palettes for the code graph.
 *
 * Responsibilities:
 * - Provide node-type and status palettes with case-insensitive label lookup
 * - Expose status legend entries whose labels carry codeGraph i18n keys
 */
const LABEL_COLORS: Record<string, string> = {
  Project: '#e11d48',
  Package: '#f97316',
  Module: '#f97316',
  Folder: '#22c55e',
  File: '#3b82f6',
  Class: '#a855f7',
  Interface: '#a855f7',
  Function: '#06b6d4',
  Method: '#06b6d4',
  Variable: '#94a3b8',
  Type: '#94a3b8',
  Route: '#eab308',
  Decorator: '#64748b',
  Section: '#cbd5e1',
  Branch: '#64748b',
  EnvVar: '#14b8a6',
};

const STATUS_COLORS: Record<string, string> = {
  dead: '#ef4444',
  single: '#f97316',
  entry: '#3b82f6',
  test: '#a855f7',
  exported: '#64748b',
  normal: '#22c55e',
  /* Structural nodes are the vast majority; a darker shade would "disappear" against the dark background. */
  structural: '#6b7280',
};

export function colorForLabel(label: string): string {
  if (!label) return '#94a3b8';
  /* Case-insensitive match. */
  const hit = LABEL_COLORS[label] || LABEL_COLORS[label[0]!.toUpperCase() + label.slice(1)];
  return hit || '#94a3b8';
}

export function colorForStatus(status: string): string {
  return STATUS_COLORS[status] || '#334155';
}

/** Status color legend, shown when "color by status" is enabled in the sidebar.
 *  `label` carries a codeGraph:status.* i18n key; render sites translate it. */
export const STATUS_LEGEND: { status: string; label: string; color: string }[] = [
  { status: 'dead', label: 'codeGraph:status.dead', color: STATUS_COLORS.dead! },
  { status: 'single', label: 'codeGraph:status.single', color: STATUS_COLORS.single! },
  { status: 'entry', label: 'codeGraph:status.entry', color: STATUS_COLORS.entry! },
  { status: 'test', label: 'codeGraph:status.test', color: STATUS_COLORS.test! },
  { status: 'normal', label: 'codeGraph:status.normal', color: STATUS_COLORS.normal! },
  { status: 'structural', label: 'codeGraph:status.structural', color: STATUS_COLORS.structural! },
];

export const LABEL_COLOR_ENTRIES = Object.entries(LABEL_COLORS);
