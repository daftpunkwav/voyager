/**
 * @file l0Layout3d
 * @description Projects the L0 project universe graph into shared GraphScene render data.
 *
 * Display-level coarsening only: clusters may be merged and scales adjusted
 * without touching edge similarity values. Layouts (compact sphere, stacked
 * tree rings, filled radial disk) target personal libraries of ~50-300 projects.
 *
 * Responsibilities:
 * - Coarsen similarity communities into display clusters for hundred-scale graphs
 * - Lay clusters out as a compact sphere, stacked tree rings or filled radial disk
 * - Project the graph into scene data and map scene nodes back to project ids
 */
import type { GraphData, GraphEdge, GraphNode } from '@/api/types';
import type { CodeGraphData, CodeGraphNode } from '@/components/code-graph/types';
import type { GraphLayoutMode } from '@/stores/graphStore';

const FORCE_ITERS_CAP = 90;
/** Golden angle: spreads points evenly inside a circle, avoiding clumped sectors. */
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

export function hashId(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h) || 1;
}

/** Color by resource kind (repo/doc/web); unknown kinds fall back to gray-blue. */
const KIND_COLORS: Record<string, string> = {
  repo: '#007aff',
  doc: '#30d158',
  web: '#ff9f0a',
};
const KIND_FALLBACK = '#5e5ce6';

function colorForProject(n: GraphNode): string {
  return KIND_COLORS[(n.kind || '').toLowerCase()] ?? KIND_FALLBACK;
}

type Vec = {
  id: string;
  x: number;
  y: number;
  z: number;
  size: number;
  foundation: number;
  hubness: number;
  clusterId: string;
  fineClusterId: string;
  stars: number;
};

type WLink = { source: string; target: string; w: number };

/** Target display-cluster count for hundred-scale graphs (the tree layer count uses the same heuristic). */
export function targetDisplayClusters(n: number): number {
  if (n <= 12) return Math.max(1, n);
  if (n <= 40) return Math.max(3, Math.min(6, Math.ceil(n / 8)));
  if (n <= 100) return Math.max(5, Math.min(8, Math.round(n / 14)));
  return Math.max(6, Math.min(10, Math.round(Math.sqrt(n) * 0.65)));
}

export function clusterRadius(memberCount: number): number {
  return 48 + Math.sqrt(Math.max(1, memberCount)) * 28;
}

/**
 * In-group relative rank: higher values map closer to 1.
 * Used for "deepest foundation / widest connections within the library" —
 * even without an absolute floor, the deepest member still sits at the center.
 */
export function relativeRankHigh(values: number[]): number[] {
  const n = values.length;
  if (n === 0) return [];
  if (n === 1) return [1];
  const order = values.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v || a.i - b.i);
  const out = new Array<number>(n).fill(0);
  order.forEach((item, rank) => {
    out[item.i] = rank / (n - 1);
  });
  return out;
}

/**
 * Filled-disk radius: centrality 1 sits at the center, 0 at the rim; the sqrt
 * curve equalizes area so the center remains reachable.
 */
export function filledDiskRadius(localR: number, centrality: number): number {
  const c = Math.max(0, Math.min(1, centrality));
  const t = 1 - c;
  return localR * (0.02 + 0.98 * Math.sqrt(t));
}

export function foundationRadius(localR: number, foundation: number): number {
  const f = Math.max(0, Math.min(1, foundation));
  return filledDiskRadius(localR, f);
}

/** @deprecated Kept for tests; for tree layouts use relative ranks plus filledDiskRadius. */
export function treeRingRadius(localR: number, foundation: number, _memberCount: number): number {
  return filledDiskRadius(localR, foundation);
}

export function hubnessRadius(maxR: number, hubness: number): number {
  return filledDiskRadius(maxR, hubness);
}

/** Layout-only: lifts the pull of weak edges; does not change real similarity. */
export function layoutEdgeWeight(w: number): number {
  return 0.22 + 0.78 * Math.max(0.05, Math.min(1, w));
}

function edgeWeight(e: GraphEdge): number {
  const s = e.similarity;
  if (typeof s === 'number' && Number.isFinite(s)) return Math.max(0.05, Math.min(1, s));
  return 0.55;
}

export function fallbackCommunities(
  nodeIds: string[],
  links: WLink[],
  minW = 0.22
): Map<string, string> {
  const parent = new Map(nodeIds.map((id) => [id, id]));
  const find = (x: string): string => {
    let p = parent.get(x)!;
    while (p !== parent.get(p)) p = parent.get(p)!;
    parent.set(x, p);
    return p;
  };
  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra === rb) return;
    if (ra < rb) parent.set(rb, ra);
    else parent.set(ra, rb);
  };
  const sorted = [...links].sort((a, b) => b.w - a.w);
  const maxMerge = Math.max(1, Math.floor(nodeIds.length * 0.92));
  let merges = 0;
  for (const e of sorted) {
    if (e.w < minW) break;
    if (merges >= maxMerge) break;
    if (find(e.source) === find(e.target)) continue;
    union(e.source, e.target);
    merges += 1;
  }
  const out = new Map<string, string>();
  for (const id of nodeIds) out.set(id, find(id));
  return out;
}

/**
 * Display-level coarsening: merges overly fine clusters down to the target
 * count without touching edge weights. Each small cluster joins the neighbor
 * with the strongest cross-cluster weight.
 */
export function coarsenClustersForDisplay(
  cluster: Map<string, string>,
  links: WLink[],
  target: number
): Map<string, string> {
  const parent = new Map<string, string>();
  const roots = new Set(cluster.values());
  for (const r of roots) parent.set(r, r);

  const find = (x: string): string => {
    let p = parent.get(x) ?? x;
    while (p !== (parent.get(p) ?? p)) p = parent.get(p)!;
    parent.set(x, p);
    return p;
  };
  const union = (a: string, b: string) => {
    const ra = find(a);
    const rb = find(b);
    if (ra === rb) return;
    if (ra < rb) parent.set(rb, ra);
    else parent.set(ra, rb);
  };

  const sizes = () => {
    const s = new Map<string, number>();
    for (const fine of cluster.values()) {
      const r = find(fine);
      s.set(r, (s.get(r) || 0) + 1);
    }
    return s;
  };

  const buildCross = () => {
    const cross = new Map<string, number>();
    for (const e of links) {
      const ca = find(cluster.get(e.source) || e.source);
      const cb = find(cluster.get(e.target) || e.target);
      if (ca === cb) continue;
      const key = ca < cb ? `${ca}|${cb}` : `${cb}|${ca}`;
      cross.set(key, (cross.get(key) || 0) + e.w);
    }
    return cross;
  };

  let sz = sizes();
  let guard = 0;
  while (sz.size > Math.max(1, target) && guard < 400) {
    guard += 1;
    const small = [...sz.entries()].sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]))[0]!;
    const cross = buildCross();
    let bestOther: string | null = null;
    let bestW = -1;
    for (const [key, w] of cross) {
      const [a, b] = key.split('|') as [string, string];
      if (a !== small[0] && b !== small[0]) continue;
      const other = a === small[0] ? b : a;
      if (!sz.has(other)) continue;
      if (w > bestW) {
        bestW = w;
        bestOther = other;
      }
    }
    if (!bestOther) {
      const large = [...sz.entries()]
        .filter(([id]) => id !== small[0])
        .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
      if (!large) break;
      bestOther = large[0];
    }
    union(small[0], bestOther);
    sz = sizes();
  }

  const out = new Map<string, string>();
  for (const [nodeId, fine] of cluster) {
    out.set(nodeId, find(fine));
  }
  return out;
}

function fibonacciDir(i: number, n: number): { x: number; y: number; z: number } {
  const m = Math.max(1, n);
  const phi = Math.acos(1 - (2 * (i + 0.5)) / m);
  const theta = Math.PI * (1 + Math.sqrt(5)) * i;
  return {
    x: Math.sin(phi) * Math.cos(theta),
    y: Math.sin(phi) * Math.sin(theta),
    z: Math.cos(phi),
  };
}

/** Inside a circle/sphere: divide into sectors per fine cluster, then spread evenly within each sector. */
function sectorAngle(members: Vec[], node: Vec, links: WLink[]): number {
  const fines = [...new Set(members.map((m) => m.fineClusterId))].sort();
  const sector = (Math.PI * 2) / Math.max(1, fines.length);
  const fi = Math.max(0, fines.indexOf(node.fineClusterId));
  const peers = members.filter((m) => m.fineClusterId === node.fineClusterId);
  const pi = Math.max(
    0,
    peers.findIndex((p) => p.id === node.id)
  );
  const local = peers.length <= 1 ? 0.5 : (pi + 0.5) / peers.length;
  const evenly = fi * sector + local * sector * 0.85 + sector * 0.075;
  if (peers.length <= 2) return evenly;
  const bias = localAngleBias(members, links, members.indexOf(node));
  return evenly * 0.82 + bias * 0.18;
}

function localAngleBias(members: Vec[], links: WLink[], idx: number): number {
  const node = members[idx]!;
  if (!node) return 0;
  const neighborW = new Map<string, number>();
  for (const e of links) {
    if (e.source === node.id) neighborW.set(e.target, e.w);
    else if (e.target === node.id) neighborW.set(e.source, e.w);
  }
  let angle = (idx / Math.max(1, members.length)) * Math.PI * 2;
  let pull = 0;
  let wSum = 0;
  members.forEach((m, j) => {
    const w = neighborW.get(m.id);
    if (!w || w < 0.25) return;
    const a = (j / Math.max(1, members.length)) * Math.PI * 2;
    pull += a * w;
    wSum += w;
  });
  if (wSum > 0) angle = 0.55 * angle + 0.45 * (pull / wSum);
  return angle;
}

function openSpread(n: number, clusterCount: number): number {
  /* Keep cluster centers moderately close so outer rings and inter-cluster gaps stay compact. */
  const base = 95 + Math.sqrt(n) * 18;
  const pack = 0.48 + 0.04 * Math.min(clusterCount, 12);
  return base * pack;
}

/** Target layer count for the tree layout. */
export function targetTreeLayerCount(n: number): number {
  if (n <= 24) return Math.max(2, Math.ceil(n / 8));
  if (n <= 80) return Math.max(4, Math.round(n / 16));
  return Math.max(5, Math.min(8, Math.round(n / 32)));
}

/**
 * Tree layering: keeps small layers on top and large ones at the bottom; only
 * splits oversized layers and merges tiny ones, avoiding over-even distribution.
 */
export function balanceTreeLayers(nodes: Vec[], links: WLink[]): Vec[][] {
  const n = nodes.length;
  if (!n) return [];
  const layersTarget = targetTreeLayerCount(n);
  /* Allow pronounced size differences: bottom layers may be several times larger than upper ones. */
  const maxPer = Math.max(28, Math.ceil(n / Math.max(3, layersTarget - 1)));
  const minPer = 2;

  const byComm = new Map<string, Vec[]>();
  for (const node of nodes) {
    if (!byComm.has(node.clusterId)) byComm.set(node.clusterId, []);
    byComm.get(node.clusterId)!.push(node);
  }

  const chunks: Vec[][] = [];
  const pushChunks = (group: Vec[]) => {
    if (group.length <= maxPer) {
      chunks.push(group);
      return;
    }
    /* Split only oversized groups, cutting along fine clusters to preserve a size gradient. */
    const byFine = new Map<string, Vec[]>();
    for (const node of group) {
      if (!byFine.has(node.fineClusterId)) byFine.set(node.fineClusterId, []);
      byFine.get(node.fineClusterId)!.push(node);
    }
    const parts = [...byFine.values()].sort((a, b) => a.length - b.length);
    let bucket: Vec[] = [];
    const flush = () => {
      if (bucket.length) {
        chunks.push(bucket);
        bucket = [];
      }
    };
    for (const part of parts) {
      if (part.length > maxPer) {
        flush();
        const ranked = part
          .slice()
          .sort((a, b) => a.foundation - b.foundation || a.id.localeCompare(b.id));
        const piece = Math.ceil(part.length / Math.ceil(part.length / maxPer));
        for (let i = 0; i < ranked.length; i += piece) {
          chunks.push(ranked.slice(i, i + piece));
        }
        continue;
      }
      if (bucket.length && bucket.length + part.length > maxPer) flush();
      bucket.push(...part);
    }
    flush();
  };

  for (const g of byComm.values()) pushChunks(g);

  const crossWeight = (a: Vec[], b: Vec[]): number => {
    const ids = new Set(b.map((x) => x.id));
    let w = 0;
    for (const e of links) {
      const aHas = a.some((x) => x.id === e.source || x.id === e.target);
      const bHas = ids.has(e.source) || ids.has(e.target);
      if (aHas && bHas) w += e.w;
    }
    return w;
  };

  /* Merge only tiny layers (1-2 nodes) to preserve the small-rings-on-top look. */
  let guard = 0;
  while (guard < 120) {
    guard += 1;
    chunks.sort((a, b) => a.length - b.length || a[0]!.id.localeCompare(b[0]!.id));
    const small = chunks[0];
    if (!small || small.length >= minPer || chunks.length <= 3) break;
    let bestJ = 1;
    let bestW = -1;
    for (let j = 1; j < Math.min(chunks.length, 6); j += 1) {
      const w = crossWeight(small, chunks[j]!);
      if (w > bestW) {
        bestW = w;
        bestJ = j;
      }
    }
    chunks[bestJ]!.push(...small);
    chunks.splice(0, 1);
  }

  while (chunks.length > layersTarget + 2) {
    chunks.sort((a, b) => a.length - b.length);
    const a = chunks.shift()!;
    const b = chunks.shift()!;
    /* Merge the two smallest layers while keeping a size spread. */
    chunks.push([...a, ...b]);
  }

  return chunks.sort((a, b) => a.length - b.length || a[0]!.id.localeCompare(b[0]!.id));
}

export function forceLayout3d(nodes: Vec[], links: WLink[], iterations = 48) {
  const n = nodes.length;
  if (!n) return;

  const byComm = new Map<string, Vec[]>();
  for (const node of nodes) {
    if (!byComm.has(node.clusterId)) byComm.set(node.clusterId, []);
    byComm.get(node.clusterId)!.push(node);
  }
  const commKeys = [...byComm.keys()].sort((a, b) => {
    const na = byComm.get(a)!.length;
    const nb = byComm.get(b)!.length;
    if (nb !== na) return nb - na;
    return a.localeCompare(b);
  });

  const centers = new Map<string, { x: number; y: number; z: number; R: number }>();
  const spread = openSpread(n, Math.max(1, commKeys.length));
  commKeys.forEach((key, i) => {
    const members = byComm.get(key)!;
    const R = clusterRadius(members.length) * (n >= 100 ? 1.12 : 1.05);
    const dir = fibonacciDir(i, Math.max(commKeys.length, 6));
    const dist = spread * (0.52 + 0.06 * Math.min(commKeys.length, 12));
    centers.set(key, {
      x: dir.x * dist,
      y: dir.y * dist * 0.75,
      z: dir.z * dist,
      R,
    });
  });

  for (const [cid, members] of byComm) {
    const c = centers.get(cid)!;
    const ranks = relativeRankHigh(members.map((m) => m.foundation));
    const sorted = members
      .map((node, i) => ({ node, rank: ranks[i]! }))
      .sort((a, b) => b.rank - a.rank || a.node.id.localeCompare(b.node.id));
    sorted.forEach((item, i) => {
      const { node, rank } = item;
      const r = Math.max(c.R * 0.18, filledDiskRadius(c.R * 1.05, rank));
      const angle = i * GOLDEN_ANGLE + sectorAngle(members, node, links) * 0.12;
      const elev = ((hashId(node.id) % 100) / 100 - 0.5) * Math.PI * 0.95;
      const dir = fibonacciDir(i, members.length);
      const mix = 0.62;
      const dx = mix * Math.cos(elev) * Math.cos(angle) + (1 - mix) * dir.x;
      const dy = mix * Math.sin(elev) + (1 - mix) * dir.y;
      const dz = mix * Math.cos(elev) * Math.sin(angle) + (1 - mix) * dir.z;
      const norm = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
      node.x = c.x + (r * dx) / norm;
      node.y = c.y + (r * dy) / norm;
      node.z = c.z + (r * dz) / norm;
    });
  }

  const idx = new Map(nodes.map((node, i) => [node.id, i]));
  const repulsion = 1600 + n * 12;
  for (let iter = 0; iter < iterations; iter += 1) {
    const fx = new Array(n).fill(0);
    const fy = new Array(n).fill(0);
    const fz = new Array(n).fill(0);

    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const a = nodes[i]!;
        const b = nodes[j]!;
        const same = a.clusterId === b.clusterId;
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const dz = a.z - b.z;
        const dist2 = dx * dx + dy * dy + dz * dz + 0.01;
        const dist = Math.sqrt(dist2);
        const force = (same ? repulsion * 1.35 : repulsion * 0.32) / dist2;
        fx[i] += (force * dx) / dist;
        fy[i] += (force * dy) / dist;
        fz[i] += (force * dz) / dist;
        fx[j] -= (force * dx) / dist;
        fy[j] -= (force * dy) / dist;
        fz[j] -= (force * dz) / dist;
      }
    }

    for (const e of links) {
      const i = idx.get(e.source);
      const j = idx.get(e.target);
      if (i == null || j == null) continue;
      const a = nodes[i]!;
      const b = nodes[j]!;
      const same = a.clusterId === b.clusterId;
      const w = layoutEdgeWeight(e.w);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dz = b.z - a.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) + 0.01;
      const restBase = same ? 78 : 95;
      const rest = restBase * (1.05 - Math.min(0.5, w * 0.6));
      const k = (same ? 0.018 : 0.012) + w * (same ? 0.038 : 0.02);
      const force = (dist - rest) * k;
      fx[i] += (force * dx) / dist;
      fy[i] += (force * dy) / dist;
      fz[i] += (force * dz) / dist;
      fx[j] -= (force * dx) / dist;
      fy[j] -= (force * dy) / dist;
      fz[j] -= (force * dz) / dist;
    }

    for (let i = 0; i < n; i += 1) {
      const node = nodes[i]!;
      const c = centers.get(node.clusterId)!;
      const pull = 0.005 + node.foundation * 0.012;
      fx[i] += (c.x - node.x) * pull;
      fy[i] += (c.y - node.y) * pull;
      fz[i] += (c.z - node.z) * pull;
      fx[i] -= node.x * 0.0008;
      fy[i] -= node.y * 0.0008;
      fz[i] -= node.z * 0.0008;
      const clamp = (v: number) => Math.max(-7.5, Math.min(7.5, v));
      node.x += clamp(fx[i]);
      node.y += clamp(fy[i]);
      node.z += clamp(fz[i]);
    }
  }
}

/** Tree layout: small rings on top, larger ones below; layer spacing uses a 1.5x multiplier. */
export function treeLayout3d(nodes: Vec[], links: WLink[]) {
  if (!nodes.length) return;
  const layers = balanceTreeLayers(nodes, links);
  const n = nodes.length;
  const gap = ((n >= 120 ? 40 : 52) / 32) * 1.5;
  const scale = n >= 120 ? 0.82 : 0.95;
  const radii = layers.map((members) => clusterRadius(members.length) * scale);

  let yCursor = 0;
  const centersY: number[] = [];
  layers.forEach((_, ci) => {
    const R = radii[ci]!;
    if (ci === 0) yCursor = 0;
    else yCursor -= (radii[ci - 1]! + R) * 0.33 + gap;
    centersY.push(yCursor);
  });

  layers.forEach((members, ci) => {
    const layerId = `tree-L${ci}-n${members.length}`;
    for (const node of members) node.clusterId = layerId;
    const R = radii[ci]!;
    const cy = centersY[ci]!;
    const ranks = relativeRankHigh(members.map((m) => m.foundation));
    const sorted = members
      .map((node, i) => ({ node, rank: ranks[i]! }))
      .sort(
        (a, b) =>
          b.rank - a.rank ||
          a.node.fineClusterId.localeCompare(b.node.fineClusterId) ||
          a.node.id.localeCompare(b.node.id)
      );

    sorted.forEach((item, i) => {
      const { node, rank } = item;
      const r = filledDiskRadius(R, rank);
      const fineBias = (hashId(node.fineClusterId) % 360) * (Math.PI / 180) * 0.12;
      const angle = i * GOLDEN_ANGLE + fineBias + sectorAngle(members, node, links) * 0.15;
      const tilt = Math.sin(angle * 1.7 + ci) * Math.min(8, R * 0.05);
      node.x = r * Math.cos(angle);
      node.y = cy + tilt;
      node.z = r * Math.sin(angle);
    });
  });

  const mid = (Math.max(...nodes.map((nd) => nd.y)) + Math.min(...nodes.map((nd) => nd.y))) / 2;
  for (const nd of nodes) nd.y -= mid - 40;
}

/**
 * Radial layout: the most broadly connected nodes (relative hubness) sit at the
 * center; the disk is fully filled and angles are spread out to avoid a hollow
 * middle and clumping.
 */
export function radialLayout3d(nodes: Vec[], links: WLink[]) {
  if (!nodes.length) return;
  const n = nodes.length;
  const maxR =
    n >= 150 ? 95 + Math.sqrt(n) * 11 : n >= 80 ? 100 + Math.sqrt(n) * 14 : 110 + Math.sqrt(n) * 22;

  const hubRanks = relativeRankHigh(nodes.map((nd) => nd.hubness));
  const byIdRank = new Map(nodes.map((nd, i) => [nd.id, hubRanks[i]!]));

  const clusters = [...new Set(nodes.map((nd) => nd.clusterId))].sort();
  const sector = (Math.PI * 2) / Math.max(1, clusters.length);

  const byComm = new Map<string, Vec[]>();
  for (const node of nodes) {
    if (!byComm.has(node.clusterId)) byComm.set(node.clusterId, []);
    byComm.get(node.clusterId)!.push(node);
  }

  let globalI = 0;
  clusters.forEach((cid, ci) => {
    const members = byComm.get(cid)!;
    const base = ci * sector + sector * 0.5;
    const sorted = members
      .slice()
      .sort(
        (a, b) => (byIdRank.get(b.id) ?? 0) - (byIdRank.get(a.id) ?? 0) || a.id.localeCompare(b.id)
      );

    sorted.forEach((node, i) => {
      const centrality = byIdRank.get(node.id) ?? 0.5;
      const r = filledDiskRadius(maxR, centrality);
      /* Primary: golden-angle spread; secondary: cluster sectors so nodes do not pile into one direction. */
      const golden = globalI * GOLDEN_ANGLE;
      const local = (i / Math.max(1, members.length)) * sector * 0.7 - sector * 0.35;
      const neighbor = localAngleBias(members, links, members.indexOf(node)) * 0.12;
      const angle = golden * 0.55 + (base + local) * 0.33 + neighbor;
      node.x = r * Math.cos(angle);
      node.y = Math.sin(angle * 2.1 + ci) * 5;
      node.z = r * Math.sin(angle);
      globalI += 1;
    });
  });
}

function resolveNodeMetrics(
  data: GraphData,
  links: WLink[]
): {
  foundation: Map<string, number>;
  hubness: Map<string, number>;
  cluster: Map<string, string>;
} {
  const foundation = new Map<string, number>();
  const hubness = new Map<string, number>();
  const cluster = new Map<string, string>();

  const hasBackendCluster = data.nodes.some((n) => n.cluster_id);
  const fallback = hasBackendCluster
    ? null
    : fallbackCommunities(
        data.nodes.map((n) => n.id),
        links,
        data.nodes.length >= 100 ? 0.16 : 0.22
      );

  const wdeg = new Map<string, number>();
  for (const e of links) {
    wdeg.set(e.source, (wdeg.get(e.source) || 0) + e.w);
    wdeg.set(e.target, (wdeg.get(e.target) || 0) + e.w);
  }
  const maxW = Math.max(1, ...wdeg.values(), 1);

  for (const n of data.nodes) {
    const cid = n.cluster_id || fallback?.get(n.id) || n.id;
    cluster.set(n.id, cid);
    const cent = (wdeg.get(n.id) || 0) / maxW;
    foundation.set(
      n.id,
      typeof n.foundation_score === 'number'
        ? n.foundation_score
        : Math.min(1, 0.25 + cent * 0.35 + Math.log1p(n.stars || 0) / 30)
    );
    hubness.set(
      n.id,
      typeof n.hubness === 'number'
        ? n.hubness
        : Math.min(1, cent * 0.7 + ((wdeg.get(n.id) || 0) > 0 ? 0.15 : 0))
    );
  }
  return { foundation, hubness, cluster };
}

export function projectGraphToScene(
  data: GraphData,
  layoutMode: GraphLayoutMode = 'force'
): CodeGraphData {
  const n = data.nodes.length;
  const edgeSparse = data.edges.length < Math.max(8, n * 0.8);
  const sizeBoost = edgeSparse ? (n >= 100 ? 1.25 : 1.55) : 1;

  const links: WLink[] = data.edges.map((e) => ({
    source: e.source,
    target: e.target,
    w: edgeWeight(e),
  }));
  const metrics = resolveNodeMetrics(data, links);
  const fine = metrics.cluster;
  const display = coarsenClustersForDisplay(fine, links, targetDisplayClusters(n));

  const vecs: Vec[] = data.nodes.map((node) => ({
    id: node.id,
    x: 0,
    y: 0,
    z: 0,
    size: Math.max(
      n >= 150 ? 2.3 : 2.5,
      /* Stars influence size only mildly to keep node sizes comparable. */
      (2.5 + Math.min(2.8, Math.log2((node.stars || 0) + 1) * 0.55)) * sizeBoost
    ),
    foundation: metrics.foundation.get(node.id) ?? 0.3,
    hubness: metrics.hubness.get(node.id) ?? 0.2,
    clusterId: display.get(node.id) ?? node.id,
    fineClusterId: fine.get(node.id) ?? node.id,
    stars: node.stars || 0,
  }));

  const iters = Math.min(FORCE_ITERS_CAP, 36 + Math.floor(n / 3));
  if (layoutMode === 'tree') treeLayout3d(vecs, links);
  else if (layoutMode === 'radial') radialLayout3d(vecs, links);
  else forceLayout3d(vecs, links, iters);

  const pos = new Map(vecs.map((v) => [v.id, v]));
  const idMap = new Map(data.nodes.map((node) => [node.id, hashId(node.id)]));
  const nodes: CodeGraphNode[] = data.nodes.map((node) => {
    const p = pos.get(node.id)!;
    return {
      id: hashId(node.id),
      x: p.x,
      y: p.y,
      z: p.z,
      label: node.kind ? `Resource:${node.kind}` : 'Project',
      name: node.name,
      kind: node.kind ? `Resource:${node.kind}` : 'Project',
      size: p.size,
      color: colorForProject(node),
      status: 'normal',
      qualified_name: node.id,
      // Project-level nodes carry no file path; reuse file_path to surface the
      // project language (GraphNode.language) in scene tooltips/filters.
      file_path: node.language || undefined,
    };
  });

  const edges = data.edges
    .map((e) => ({
      source: idMap.get(e.source)!,
      target: idMap.get(e.target)!,
      type: e.edge_type || e.relation || 'related',
      relation: e.edge_type || e.relation || 'related',
    }))
    .filter((e) => e.source && e.target);

  return {
    nodes,
    edges,
    stats: { node_count: nodes.length, edge_count: edges.length },
  };
}

export function applySelectionRelatedness(
  scene: CodeGraphData,
  data: GraphData,
  selectedProjectId: string | null
): CodeGraphData {
  if (!selectedProjectId) {
    return {
      ...scene,
      nodes: scene.nodes.map((node) => {
        const { relatedness: _, ...rest } = node as CodeGraphNode & {
          relatedness?: number;
        };
        return { ...rest };
      }),
    };
  }
  const sim = new Map<string, number>();
  for (const e of data.edges) {
    if (e.source === selectedProjectId) sim.set(e.target, e.similarity);
    else if (e.target === selectedProjectId) sim.set(e.source, e.similarity);
  }
  return {
    ...scene,
    nodes: scene.nodes.map((node) => {
      const pid = node.qualified_name;
      if (!pid || pid === selectedProjectId) {
        const { relatedness: _, ...rest } = node as CodeGraphNode & {
          relatedness?: number;
        };
        return { ...rest };
      }
      const s = sim.get(pid);
      if (s == null) {
        const { relatedness: _, ...rest } = node as CodeGraphNode & {
          relatedness?: number;
        };
        return { ...rest };
      }
      return { ...node, relatedness: s };
    }),
  };
}

export function projectIdFromSceneNode(node: CodeGraphNode, data: GraphData): string | null {
  const hit = data.nodes.find((n) => hashId(n.id) === node.id);
  return hit?.id ?? null;
}

export function treeClusterOrderY(nodes: Vec[]): string[] {
  const by = new Map<string, { y: number; n: number }>();
  for (const node of nodes) {
    const cur = by.get(node.clusterId);
    if (!cur) by.set(node.clusterId, { y: node.y, n: 1 });
    else {
      cur.y += node.y;
      cur.n += 1;
    }
  }
  return [...by.entries()]
    .map(([id, v]) => ({ id, y: v.y / v.n, n: v.n }))
    .sort((a, b) => a.y - b.y)
    .map((x) => x.id);
}
