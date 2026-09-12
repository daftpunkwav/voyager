/**
 * @file labelLayout
 * @description Label density rules for the graph: budgets, priorities, and
 * screen-space non-overlap picking.
 *
 * Responsibilities:
 * - Score label priority from kind weight, call count and node size
 * - Budget visible labels by camera distance and cap the world font size
 * - Greedily keep non-overlapping labels in screen space
 * - Normalize display names (strip wrapping quotes, keep the last path segment)
 */

export const LABEL_KIND_WEIGHT: Record<string, number> = {
  Project: 80,
  Package: 60,
  Module: 55,
  Folder: 50,
  File: 40,
  Class: 35,
  Interface: 32,
  Route: 30,
  Function: 28,
  Method: 24,
  Type: 18,
  Field: 8,
  Variable: 6,
  Macro: 6,
  Section: 4,
  Decorator: 4,
};

export function labelPriority(node: {
  kind?: string;
  label?: string;
  size?: number;
  in_calls?: number;
}): number {
  const kind = node.kind || node.label || '';
  const kindBonus = LABEL_KIND_WEIGHT[kind] ?? 10;
  return (node.in_calls || 0) * 12 + (node.size || 0) * 2 + kindBonus;
}

/** Fewer labels as the camera moves away, keeping the galaxy overview from turning into a wall of text. */
export function labelBudgetForDistance(dist: number, maxLabels: number): number {
  if (!Number.isFinite(dist) || dist <= 0) return Math.min(16, maxLabels);
  if (dist >= 2500) return Math.min(8, maxLabels);
  if (dist >= 1600) return Math.min(14, maxLabels);
  if (dist >= 900) return Math.min(22, maxLabels);
  if (dist >= 450) return Math.min(32, maxLabels);
  return Math.min(maxLabels, 40);
}

/** World font size: grows slightly with distance for readability, but is hard-capped to prevent giant overlapping text in the overview. */
export function labelWorldFontSize(dist: number, nodeSize: number): number {
  const byNode = Math.max(1.6, (nodeSize || 4) * 0.38);
  const byDist = Math.min(14, dist * 0.0065);
  return Math.min(14, Math.max(byNode, byDist));
}

export interface ProjectedLabel {
  id: number;
  x: number;
  y: number;
  w: number;
  h: number;
  priority: number;
}

/** Greedily keep non-overlapping labels by priority (screen pixel coordinates). */
export function pickNonOverlappingLabels(
  items: ProjectedLabel[],
  maxKeep: number,
  padding = 4
): Set<number> {
  const sorted = [...items].sort((a, b) => b.priority - a.priority);
  const kept: ProjectedLabel[] = [];
  const ids = new Set<number>();

  for (const item of sorted) {
    if (ids.size >= maxKeep) break;
    const overlaps = kept.some(
      (k) =>
        Math.abs(k.x - item.x) * 2 < k.w + item.w + padding &&
        Math.abs(k.y - item.y) * 2 < k.h + item.h + padding
    );
    if (overlaps) continue;
    kept.push(item);
    ids.add(item.id);
  }
  return ids;
}

/** Display name: strip wrapping quotes; further truncation is handled on the texture side. */
export function shortenLabelName(raw: string): string {
  let s = (raw || '').trim();
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    s = s.slice(1, -1);
  }
  if (s.includes('/') && !s.includes(' ')) {
    const parts = s.split('/');
    s = parts[parts.length - 1] || s;
  }
  return s;
}
