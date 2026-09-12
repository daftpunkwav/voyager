/**
 * @file provider
 * @description Page probe for the graph page: node/edge counts plus the currently selected node.
 *
 * Does not guess at the query cache shape (useGraph's queryKey includes the
 * filter). GraphPage writes the current view's nodes/edges lengths into this
 * module-level cache; the provider is read-only.
 *
 * Responsibilities:
 * - Hold the module-level snapshot cache (counts plus selected node)
 *   written by GraphPage
 * - Report a localized index line with counts, a selected-node suffix, and
 *   the selected id; null while data is missing
 */

import type { PageProbe } from '@/bridge/pageContext';
import { i18n } from '@/i18n';

export interface GraphSnapshot {
  nodes: number;
  edges: number;
  selectedId: string;
  selectedName: string;
}

let snapshot: GraphSnapshot | null = null;

/** Records the snapshot when data arrives; null means not ready or page exited (reported as no data). */
export function rememberGraphSnapshot(next: GraphSnapshot | null): void {
  snapshot = next;
}

export function lastGraphSnapshot(): GraphSnapshot | null {
  return snapshot;
}

export const graphProvider: PageProbe = {
  page: 'graph',
  report() {
    const s = snapshot;
    if (!s) return null;
    const name = s.selectedName.trim().slice(0, 40);
    const summary =
      i18n.t('graph:probe.summary', { nodes: s.nodes, edges: s.edges }) +
      (name ? i18n.t('graph:probe.selectedSuffix', { name }) : '');
    return {
      summary,
      counts: { nodes: s.nodes, edges: s.edges },
      selected: s.selectedId || undefined,
    };
  },
};
