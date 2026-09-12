/**
 * @file provider
 * @description Page-awareness probe for the code graph page.
 *
 * Reports the selected project id as soon as it is known; node/edge counts stay
 * null until layout data arrives (never fabricate numbers).
 *
 * Responsibilities:
 * - Hold the module-level snapshot cache (project id plus counts) written
 *   by CodeGraphPage
 * - Report the project id as the selected row and a localized index line,
 *   omitting counts until layout data arrives
 * - Report under the graph page field (the backend groups code graphs in
 *   the graph domain)
 */

import type { PageProbe } from '@/bridge/pageContext';
import { i18n } from '@/i18n';

export interface CodeGraphSnapshot {
  projectId: string;
  /** null = layout data not ready (no fabricated numbers) */
  nodes: number | null;
  edges: number | null;
}

let snapshot: CodeGraphSnapshot | null = null;

/** Write as soon as the project id is known; update counts once layout data arrives. */
export function rememberCodeGraphDetail(next: CodeGraphSnapshot | null): void {
  snapshot = next;
}

export function lastCodeGraphDetail(): CodeGraphSnapshot | null {
  return snapshot;
}

export const codeGraphProvider: PageProbe = {
  // The backend also belongs to the graph domain, so the reported page field stays "graph"
  page: 'graph',
  report() {
    const s = snapshot;
    if (!s) return null;
    const countPart =
      s.nodes === null
        ? ''
        : i18n.t('codeGraph:probe.counts', { nodes: s.nodes, edges: s.edges ?? 0 });
    const counts = s.nodes === null ? undefined : { nodes: s.nodes, edges: s.edges ?? 0 };
    return {
      summary: i18n.t('codeGraph:probe.summary', { projectId: s.projectId }) + countPart,
      counts,
      selected: s.projectId,
    };
  },
};
