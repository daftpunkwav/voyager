/**
 * @file l0EdgeTypes
 * @description L0 edge type catalog and legend colors, matching the edge types produced by the backend L0 pipeline.
 *
 * Functional data (edge type ids and colors) stays literal. Display copy lives
 * in the graph namespace (edgeType.* / edge.all); the `label` field carries the
 * i18n key and is translated at render sites. Backend error classification
 * lives in utils/graphErrorKind.ts.
 *
 * Responsibilities:
 * - Define the L0 edge type catalog and legend colors as literal data
 * - Translate edge type ids into display labels at render time
 */
import { i18n } from '@/i18n';

export const L0_EDGE_TYPES = [
  { id: 'related', label: 'graph:edgeType.related', color: '#2dd4bf' },
  { id: 'cross_repo', label: 'graph:edgeType.cross_repo', color: '#fb923c' },
] as const;

export type L0EdgeTypeId = (typeof L0_EDGE_TYPES)[number]['id'];

export const L0_EDGE_COLOR_MAP: Record<string, string> = Object.fromEntries(
  L0_EDGE_TYPES.map((edge) => [edge.id, edge.color])
);

export function labelForEdgeType(id: string | null | undefined): string {
  if (!id) return i18n.t('graph:edge.all');
  const hit = L0_EDGE_TYPES.find((edge) => edge.id === id);
  return hit ? i18n.t(hit.label) : id;
}
