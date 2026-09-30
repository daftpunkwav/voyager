/**
 * @file graph.ts
 * @description Graph domain (L0): universe view and analysis enqueue.
 *
 * L1 code-graph index management lives in api/codeGraph.ts; the two page
 * domains evolve independently. All functions return payloads directly,
 * without a {data} envelope.
 *
 * Responsibilities:
 * - Call the graph capability (l0_view / enqueue_l0)
 * - Map backend L0 rows onto the display GraphData shape (the single mapping
 *   point for that conversion; hooks only bind it to the query cache)
 */

import { callCapability } from '@/bridge/client';
import type { GraphData, GraphEdge, GraphNode } from '@/api/types';

/** L0 view: `kinds` selects a subset of resource kinds (empty or undefined = all). */
export function getGraph(p?: { kinds?: string[]; limit?: number }): Promise<unknown> {
  return callCapability('graph', 'l0_view', (p ?? {}) as Record<string, unknown>);
}

/** Enqueue L0 association analysis (kinds subset of repo/doc/web). */
export function enqueueL0(kinds: string[], priority = 100): Promise<unknown> {
  return callCapability('graph', 'enqueue_l0', { kinds, priority });
}

/** Backend l0_view row shape (store rows; attrs already an object) */
interface L0NodeRow {
  id: string;
  label: string;
  name: string;
  qualified_name: string;
  attrs: {
    kind?: string;
    tags?: string[];
    category?: string;
    status?: string;
    subtitle?: string;
  };
}

interface L0EdgeRow {
  id?: string;
  src: string;
  dst: string;
  type: string;
  attrs: Record<string, unknown>;
}

/** Backend l0_view payload shape. */
export interface L0View {
  nodes: L0NodeRow[];
  edges: L0EdgeRow[];
  cross_edges: L0EdgeRow[];
}

const EMPTY_L0_VIEW: L0View = { nodes: [], edges: [], cross_edges: [] };

/** Normalize RELATED edge weight: 1 shared tag = 1/3, capped at 1 for >=3. */
function relatedWeight(shared: unknown): number {
  const n = Array.isArray(shared) ? shared.length : 1;
  return Math.min(1, n / 3);
}

/** Backend L0 rows -> display graph data (node metadata goes into GraphNode extension fields) */
export function toGraphData(view: L0View): GraphData {
  const nodes: GraphNode[] = view.nodes.map((n) => ({
    id: n.id,
    name: n.name,
    stars: 0,
    kind: (n.attrs.kind as GraphNode['kind']) ?? undefined,
    tags: n.attrs.tags ?? [],
    category: n.attrs.category ?? '',
    status: n.attrs.status ?? '',
    description: n.attrs.subtitle ?? '',
    /** qualified_name = "{kind}:{resource id}"; used to jump to the resource detail. */
    resourceId: n.qualified_name.includes(':')
      ? n.qualified_name.split(':').slice(1).join(':')
      : n.qualified_name,
  }));
  const edges: GraphEdge[] = [
    ...view.edges.map((e) => ({
      source: e.src,
      target: e.dst,
      similarity: relatedWeight(e.attrs.shared_tags),
      edge_type: e.type.toLowerCase(),
    })),
    ...view.cross_edges.map((e) => ({
      source: e.src,
      target: e.dst,
      similarity: 1,
      edge_type: e.type.toLowerCase(),
    })),
  ];
  return { nodes, edges };
}

/** L0 display graph: l0_view payload -> GraphData. A missing payload degrades
 *  to the empty view (the hook renders an empty universe, not an error). */
export async function getGraphData(p?: { kinds?: string[]; limit?: number }): Promise<GraphData> {
  const res = await getGraph(p);
  return toGraphData((res ?? EMPTY_L0_VIEW) as L0View);
}
