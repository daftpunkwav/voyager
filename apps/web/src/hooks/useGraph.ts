/**
 * @file useGraph
 * @description Data source for the L0 universe graph (graph.l0_view); the node
 * kinds filter lives in the graph store.
 *
 * The hook only binds the store filter to the query cache; the backend
 * L0 row -> GraphData mapping lives in api/graph.ts (the api layer is the
 * single mapping point for that conversion).
 */

import { useQuery } from '@tanstack/react-query';
import { getGraphData } from '@/api/graph';
import { useGraphStore } from '@/stores/graphStore';

/** L0 universe graph data source: graph.l0_view (kinds decided by the store). */
export function useGraph() {
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const maxEdges = useGraphStore((s) => s.maxEdges);
  const kinds = kindsFilter ? [...kindsFilter] : undefined;

  return useQuery({
    queryKey: ['graph-l0', kinds, maxEdges],
    queryFn: () => getGraphData({ kinds, limit: maxEdges }),
  });
}
