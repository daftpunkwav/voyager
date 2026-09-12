/**
 * @file useGraph
 * @description Data source for the L0 universe graph (graph.l0_view); the node
 * kinds filter lives in the graph store.
 *
 * Responsibilities:
 * - Query graph.l0_view with the store's kinds filter and edge cap
 * - Convert backend L0 rows into display GraphData: RELATED weights from
 *   shared tags, cross-repo edges pinned at full weight, resource ids
 *   parsed from qualified_name
 */

import { useQuery } from '@tanstack/react-query';
import { getGraph } from '@/api/graph';
import type { GraphData, GraphEdge, GraphNode } from '@/api/types';
import { useGraphStore } from '@/stores/graphStore';

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

interface L0View {
  nodes: L0NodeRow[];
  edges: L0EdgeRow[];
  cross_edges: L0EdgeRow[];
}

/** Normalize RELATED edge weight: 1 shared tag = 1/3, capped at 1 for >=3. */
function relatedWeight(shared: unknown): number {
  const n = Array.isArray(shared) ? shared.length : 1;
  return Math.min(1, n / 3);
}

/** Backend L0 rows -> display graph data (node metadata goes into GraphNode extension fields) */
function toGraphData(view: L0View): GraphData {
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

/** L0 universe graph data source: graph.l0_view (kinds decided by the store). */
export function useGraph() {
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const maxEdges = useGraphStore((s) => s.maxEdges);
  const kinds = kindsFilter ? [...kindsFilter] : undefined;

  return useQuery({
    queryKey: ['graph-l0', kinds, maxEdges],
    queryFn: async () => {
      const res = await getGraph({ kinds, limit: maxEdges });
      return toGraphData((res ?? { nodes: [], edges: [], cross_edges: [] }) as L0View);
    },
  });
}
