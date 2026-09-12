/**
 * @file graphConstants
 * @description Display constants shared by the graph page (GraphPage and its subcomponents).
 *
 * Label fields carry i18n keys in the graph namespace (kind.* / viewMode.*);
 * they resolve to display strings at the render sites via t().
 */

import type { GraphViewMode } from '@/stores/graphStore';

/** Number of items shown per similar-resource preview page. */
export const SIMILAR_PREVIEW_COUNT = 3;

/** Resource-kind ids mapped to graph:kind.* label keys. */
export const KIND_LABELS: Record<string, string> = {
  repo: 'graph:kind.repo',
  doc: 'graph:kind.doc',
  web: 'graph:kind.web',
};

/** Available view modes; category aggregation is intentionally absent (low information density and redundant with the list/legend).
 *  Label fields are graph:viewMode.* keys resolved at render. */
export const VIEW_MODES: { id: GraphViewMode; label: string }[] = [
  { id: 'force', label: 'graph:viewMode.force' },
  { id: 'list', label: 'graph:viewMode.list' },
];
