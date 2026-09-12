/**
 * @file renderGraph
 * @description Converts backend graph data into the render-ready structure,
 * resolving numeric node ids and colors.
 *
 * Responsibilities:
 * - Map backend nodes and edges onto numeric render ids
 * - Prefer the engine-provided node color, falling back to type-based colors
 * - Normalize coordinates, sizes and relations; drop unresolvable edges
 */
import type { CodeGraphData, CodeGraphEdge, CodeGraphNode, NodeStatus } from './types';
import type { RawSubgraph } from '@/api/codeGraph';
import { colorForLabel } from './colors';

function resolveNumericId(rawId: unknown, fallbackIdx: number, idMap: Map<string, number>): number {
  if (typeof rawId === 'number' && Number.isFinite(rawId)) {
    idMap.set(String(rawId), rawId);
    return rawId;
  }
  const key = String(rawId ?? fallbackIdx);
  if (/^\d+$/.test(key)) {
    const n = Number(key);
    idMap.set(key, n);
    return n;
  }
  const existing = idMap.get(key);
  if (existing !== undefined) return existing;
  idMap.set(key, fallbackIdx);
  return fallbackIdx;
}

/** Convert backend UnifiedGraphData into the render-ready structure. */
export function toRenderGraph(raw: RawSubgraph): CodeGraphData {
  const idMap = new Map<string, number>();
  const nodes: CodeGraphNode[] = (raw.nodes || []).map((n, idx) => {
    const kind = String(n.kind ?? n.label ?? 'Unknown');
    /* Prefer the engine-provided node color (n.color); fall back to type-based coloring. */
    const engineColor =
      typeof n.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(n.color) ? n.color : null;
    const color = engineColor || colorForLabel(kind);
    return {
      id: resolveNumericId(n.id, idx, idMap),
      x: Number(n.x ?? 0),
      y: Number(n.y ?? 0),
      z: Number(n.z ?? 0),
      label: kind,
      name: String(n.name ?? ''),
      kind,
      file_path: (n.file_path as string) || undefined,
      qualified_name: (n.qualified_name as string) || undefined,
      start_line: n.start_line as number | undefined,
      end_line: n.end_line as number | undefined,
      size: Math.max(Number(n.size ?? 1) * 1.25, 1.4),
      color,
      status: n.status as NodeStatus | undefined,
      in_calls: n.in_calls as number | undefined,
    };
  });
  const edges: CodeGraphEdge[] = [];
  for (const e of raw.edges || []) {
    const sKey = String(e.source ?? '');
    const tKey = String(e.target ?? '');
    const source = idMap.get(sKey);
    const target = idMap.get(tKey);
    if (source === undefined || target === undefined) continue;
    edges.push({
      source,
      target,
      type: String(e.relation ?? e.type ?? 'RELATED'),
      relation: String(e.relation ?? e.type ?? 'RELATED'),
    });
  }
  return {
    nodes,
    edges,
    total_nodes: raw.stats?.total_nodes ?? raw.stats?.node_count ?? nodes.length,
    stats: {
      node_count: raw.stats?.node_count ?? nodes.length,
      edge_count: raw.stats?.edge_count ?? edges.length,
      total_nodes: raw.stats?.total_nodes,
    },
  };
}
