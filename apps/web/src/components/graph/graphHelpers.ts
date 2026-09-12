/**
 * @file graphHelpers
 * @description Pure helpers for querying graph data, such as similar-node lookup by edge similarity.
 */
import type { GraphData, GraphNode } from '@/api/types';

export function getSimilarNodes(
  data: GraphData | undefined,
  nodeId: string,
  limit = 12
): { node: GraphNode; similarity: number }[] {
  if (!data) return [];
  const nodeById = new Map(data.nodes.map((n) => [n.id, n]));
  const related = data.edges
    .filter((e) => e.source === nodeId || e.target === nodeId)
    .map((e) => ({
      id: e.source === nodeId ? e.target : e.source,
      similarity: e.similarity,
    }))
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, limit);

  return related
    .map((r) => {
      const node = nodeById.get(r.id);
      return node ? { node, similarity: r.similarity } : null;
    })
    .filter((x): x is { node: GraphNode; similarity: number } => x !== null);
}
