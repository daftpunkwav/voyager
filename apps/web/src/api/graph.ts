/**
 * @file graph.ts
 * @description Graph domain (L0): universe view and analysis enqueue.
 *
 * L1 code-graph index management lives in api/codeGraph.ts; the two page
 * domains evolve independently. All functions return payloads directly,
 * without a {data} envelope.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';

/** L0 view: `kinds` selects a subset of resource kinds (empty or undefined = all). */
export function getGraph(p?: { kinds?: string[]; limit?: number }): Promise<unknown> {
  return callCapability('graph', 'l0_view', (p ?? {}) as Record<string, unknown>).then(
    unwrapDataField
  );
}

/** Enqueue L0 association analysis (kinds subset of repo/doc/web). */
export function enqueueL0(kinds: string[], priority = 100): Promise<unknown> {
  return callCapability('graph', 'enqueue_l0', { kinds, priority }).then(unwrapDataField);
}
