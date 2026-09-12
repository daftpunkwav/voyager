/**
 * @file l1Layout
 * @description Client-side layout modes for the code graph.
 *
 * "engine" keeps the engine layout3d galaxy coordinates; "force" / "tree" /
 * "radial" re-layout nodes client-side into directory spheres or
 * architectural layers.
 *
 * Responsibilities:
 * - Keep engine galaxy coordinates untouched for the "engine" mode
 * - Re-layout nodes client-side into top-level-directory spheres ("force" mode)
 * - Group nodes into architectural layers for the "tree" and "radial" modes
 * - Pack group members on a jittered Fibonacci sphere to avoid blocky shapes
 */
import type { CodeGraphData, CodeGraphNode } from './types';

export type L1LayoutMode = 'engine' | 'force' | 'tree' | 'radial';

const LAYER_GAP = 280;
const SPHERE_GAP = 380;

function topDir(fp?: string): string {
  if (!fp) return '_';
  const parts = fp.split(/[/\\]/).filter(Boolean);
  return parts[0] || '_';
}

function archLayer(n: CodeGraphNode): number {
  const p = `${n.file_path || ''} ${n.kind || ''} ${n.label || ''}`.toLowerCase();
  if (/(\bdb\b|database|sql|prisma|drizzle|migration|schema|model|entity|repository)/.test(p))
    return 0;
  if (/(cache|redis|memcache|kvstore)/.test(p)) return 1;
  if (/(api|server|backend|service|route|controller|handler|grpc|endpoint)/.test(p)) return 2;
  if (/(agent|middleware|mediator|queue|mq|bus|worker|orchestr)/.test(p)) return 3;
  if (/(web|ui|frontend|component|page|view|client|app\/|apps\/)/.test(p)) return 4;
  const depth = (n.file_path || '').split(/[/\\]/).filter(Boolean).length;
  return Math.min(4, Math.max(0, 4 - Math.min(depth, 4)));
}

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Fibonacci-sphere packing within a group, so engine coordinates do not collapse into blocky shapes. */
function packSphere(
  members: CodeGraphNode[],
  cx: number,
  cy: number,
  cz: number,
  radius: number
): CodeGraphNode[] {
  const m = members.length;
  return members.map((n, i) => {
    const phi = Math.acos(1 - (2 * (i + 0.5)) / Math.max(1, m));
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const jitter = ((hash(String(n.id)) % 100) / 100 - 0.5) * radius * 0.12;
    const r = radius + jitter;
    return {
      ...n,
      x: cx + r * Math.sin(phi) * Math.cos(theta),
      y: cy + r * Math.sin(phi) * Math.sin(theta),
      z: cz + r * Math.cos(phi),
      /* Boost size for readability. */
      size: Math.max(n.size * 1.35, 1.8),
    };
  });
}

function forceSpheres(nodes: CodeGraphNode[]): CodeGraphNode[] {
  const groups = new Map<string, CodeGraphNode[]>();
  for (const n of nodes) {
    const key = topDir(n.file_path);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(n);
  }
  const keys = [...groups.keys()].sort();
  const out: CodeGraphNode[] = [];
  keys.forEach((key, gi) => {
    const angle = (gi / Math.max(1, keys.length)) * Math.PI * 2;
    const R = SPHERE_GAP * (0.6 + Math.sqrt(keys.length) * 0.38);
    const cx = Math.cos(angle) * R;
    const cy = Math.sin(angle) * R * 0.28;
    const cz = Math.sin(angle * 1.7) * R * 0.55;
    const members = groups.get(key)!;
    const localR = 36 + Math.sqrt(members.length) * 9;
    out.push(...packSphere(members, cx, cy, cz, localR));
  });
  return out;
}

function treeLayers(nodes: CodeGraphNode[]): CodeGraphNode[] {
  const byLayer = new Map<number, CodeGraphNode[]>();
  for (const n of nodes) {
    const L = archLayer(n);
    if (!byLayer.has(L)) byLayer.set(L, []);
    byLayer.get(L)!.push(n);
  }
  const out: CodeGraphNode[] = [];
  for (const [L, members] of byLayer) {
    const y = (L - 2) * LAYER_GAP;
    /* Within a layer, cluster by top-level directory to avoid a uniform flat grid. */
    const groups = new Map<string, CodeGraphNode[]>();
    for (const n of members) {
      const k = topDir(n.file_path);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(n);
    }
    const keys = [...groups.keys()].sort();
    keys.forEach((key, gi) => {
      const ang = (gi / Math.max(1, keys.length)) * Math.PI * 2;
      const ringR = 90 + Math.sqrt(keys.length) * 55;
      const cx = Math.cos(ang) * ringR;
      const cz = Math.sin(ang) * ringR;
      const g = groups.get(key)!;
      const localR = 22 + Math.sqrt(g.length) * 7;
      out.push(
        ...packSphere(g, cx, y, cz, localR).map((n) => ({
          ...n,
          y: y + (n.y - y) * 0.25,
        }))
      );
    });
  }
  return out;
}

function radialLayers(nodes: CodeGraphNode[]): CodeGraphNode[] {
  const byLayer = new Map<number, CodeGraphNode[]>();
  for (const n of nodes) {
    const L = archLayer(n);
    if (!byLayer.has(L)) byLayer.set(L, []);
    byLayer.get(L)!.push(n);
  }
  const out: CodeGraphNode[] = [];
  for (const [L, members] of byLayer) {
    const rBase = 60 + L * (LAYER_GAP * 0.95);
    const groups = new Map<string, CodeGraphNode[]>();
    for (const n of members) {
      const k = topDir(n.file_path);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(n);
    }
    const keys = [...groups.keys()].sort();
    keys.forEach((key, gi) => {
      const ang = (gi / Math.max(1, keys.length)) * Math.PI * 2;
      const r = rBase + (hash(key) % 40);
      const cx = r * Math.cos(ang);
      const cz = r * Math.sin(ang);
      const cy = (L - 2) * (LAYER_GAP * 0.35);
      const g = groups.get(key)!;
      const localR = 20 + Math.sqrt(g.length) * 6.5;
      out.push(
        ...packSphere(g, cx, cy, cz, localR).map((n) => ({
          ...n,
          size: Math.max(n.size, 2.2),
        }))
      );
    });
  }
  return out;
}

export function applyL1Layout(data: CodeGraphData, mode: L1LayoutMode): CodeGraphData {
  if (!data.nodes.length) return data;
  /* Engine layout: keep x/y/z (galaxy coordinates from layout3d), only slightly enlarge points. */
  if (mode === 'engine') {
    return {
      ...data,
      nodes: data.nodes.map((n) => ({
        ...n,
        size: Math.max(n.size * 1.1, 1.5),
      })),
    };
  }
  let nodes = data.nodes;
  if (mode === 'force') nodes = forceSpheres(nodes);
  else if (mode === 'tree') nodes = treeLayers(nodes);
  else if (mode === 'radial') nodes = radialLayers(nodes);
  return { ...data, nodes };
}
