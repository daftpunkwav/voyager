/**
 * @file ForceGraph
 * @description D3 SVG graph supporting force, tree and radial layouts with wheel zoom and drag.
 *
 * The D3 simulation is rebuilt only when data, size or layout mode changes;
 * selection/highlight updates and zoom commands patch the SVG in place so
 * the viewport is never reset.
 *
 * Responsibilities:
 * - Run the D3 simulation for force / tree / radial layouts inside an SVG viewport
 * - Rebuild the simulation only when data, size or layout mode changes
 * - Patch selection, highlight and zoom commands in place without viewport resets
 * - Support wheel zoom and node dragging
 */
import { useEffect, useRef } from 'react';

import * as d3 from 'd3';
import type { D3DragEvent, SimulationLinkDatum, SimulationNodeDatum } from 'd3';
import type { GraphData, GraphNode } from '@/api/types';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphLayoutMode } from '@/stores/graphStore';

export const FORCE_CONFIG = {
  linkDistance: 80,
  chargeStrength: -200,
  collideRadius: 12,
};

interface ForceGraphProps {
  data: GraphData;
  width: number;
  height: number;
  onNodeClick: (node: GraphNode) => void;
  onNodeDoubleClick: (node: GraphNode) => void;
}

type SimNode = SimulationNodeDatum & GraphNode;

type SimLink = SimulationLinkDatum<SimNode> & { similarity: number };

/** Derives a stable color index (1-8) from a node id. */
function colorIndexForId(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash << 5) - hash + id.charCodeAt(i);
    hash |= 0;
  }
  return (Math.abs(hash) % 8) + 1;
}

function applyTreeLayout(nodes: SimNode[], links: SimLink[], width: number, height: number) {
  if (!nodes.length) return;
  const rootNode = [...nodes].sort((a, b) => (b.stars || 0) - (a.stars || 0))[0]!;
  const children = new Map<string, string[]>();
  const seen = new Set<string>([rootNode.id]);
  for (const link of links) {
    const s = (link.source as SimNode).id;
    const t = (link.target as SimNode).id;
    if (!children.has(s)) children.set(s, []);
    if (!children.has(t)) children.set(t, []);
  }
  // BFS to build a spanning tree, which avoids cycles.
  const queue = [rootNode.id];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const link of links) {
      const s = (link.source as SimNode).id;
      const t = (link.target as SimNode).id;
      let child: string | null = null;
      if (s === cur && !seen.has(t)) child = t;
      if (t === cur && !seen.has(s)) child = s;
      if (!child) continue;
      seen.add(child);
      children.get(cur)!.push(child);
      queue.push(child);
    }
  }
  const orphan = nodes.filter((n) => !seen.has(n.id));
  for (const n of orphan) {
    children.get(rootNode.id)!.push(n.id);
    seen.add(n.id);
  }

  type StratRow = { id: string; parentId: string | null };
  const stratifyData: StratRow[] = nodes.map((n) => ({
    id: n.id,
    parentId: n.id === rootNode.id ? null : findParent(n.id, children, rootNode.id),
  }));

  try {
    const root = d3
      .stratify<StratRow>()
      .id((d) => d.id)
      .parentId((d) => d.parentId)(stratifyData);
    const treeLayout = d3.tree<StratRow>().size([width - 80, height - 80]);
    const laid = treeLayout(root);
    laid.each((d) => {
      const node = nodes.find((n) => n.id === d.id);
      if (node) {
        node.x = (d.x ?? 0) + 40;
        node.y = (d.y ?? 0) + 40;
        node.fx = node.x;
        node.fy = node.y;
      }
    });
  } catch {
    // Fallback: simple grid.
    nodes.forEach((n, i) => {
      const cols = Math.ceil(Math.sqrt(nodes.length));
      n.x = 60 + (i % cols) * ((width - 120) / Math.max(1, cols));
      n.y = 60 + Math.floor(i / cols) * 56;
      n.fx = n.x;
      n.fy = n.y;
    });
  }
}

function findParent(id: string, children: Map<string, string[]>, rootId: string): string | null {
  for (const [parent, kids] of children) {
    if (kids.includes(id)) return parent;
  }
  return id === rootId ? null : rootId;
}

function applyRadialLayout(nodes: SimNode[], links: SimLink[], width: number, height: number) {
  if (!nodes.length) return;
  const cx = width / 2;
  const cy = height / 2;
  const rootNode = [...nodes].sort((a, b) => (b.stars || 0) - (a.stars || 0))[0]!;
  // Layer nodes by hop distance from the root.
  const dist = new Map<string, number>([[rootNode.id, 0]]);
  const q = [rootNode.id];
  const adj = new Map<string, string[]>();
  for (const n of nodes) adj.set(n.id, []);
  for (const link of links) {
    const s = (link.source as SimNode).id;
    const t = (link.target as SimNode).id;
    adj.get(s)?.push(t);
    adj.get(t)?.push(s);
  }
  while (q.length) {
    const cur = q.shift()!;
    for (const nb of adj.get(cur) || []) {
      if (dist.has(nb)) continue;
      dist.set(nb, (dist.get(cur) || 0) + 1);
      q.push(nb);
    }
  }
  const byRing = new Map<number, SimNode[]>();
  for (const n of nodes) {
    const d = dist.get(n.id) ?? 1;
    if (!byRing.has(d)) byRing.set(d, []);
    byRing.get(d)!.push(n);
  }
  const maxR = Math.min(width, height) * 0.42;
  for (const [ring, ringNodes] of byRing) {
    const r = ring === 0 ? 0 : (ring / Math.max(1, byRing.size - 1 || 1)) * maxR;
    ringNodes.forEach((n, i) => {
      const angle = (i / Math.max(1, ringNodes.length)) * Math.PI * 2 - Math.PI / 2;
      n.x = cx + r * Math.cos(angle);
      n.y = cy + r * Math.sin(angle);
      n.fx = n.x;
      n.fy = n.y;
    });
  }
}

export function ForceGraph({
  data,
  width,
  height,
  onNodeClick,
  onNodeDoubleClick,
}: ForceGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const highlightNodeId = useGraphStore((s) => s.highlightNodeId);
  const layoutMode = useGraphStore((s) => s.layoutMode);
  const zoomDirection = useGraphStore((s) => s.zoomDirection);
  const zoomTick = useGraphStore((s) => s.zoomTick);
  const setZoomLevel = useGraphStore((s) => s.setZoomLevel);
  // Hold callbacks in refs so new function identities from parent renders do
  // not rebuild the whole graph (which would reset wheel/zoom state).
  const onNodeClickRef = useRef(onNodeClick);
  const onNodeDoubleClickRef = useRef(onNodeDoubleClick);
  const setZoomLevelRef = useRef(setZoomLevel);
  onNodeClickRef.current = onNodeClick;
  onNodeDoubleClickRef.current = onNodeDoubleClick;
  setZoomLevelRef.current = setZoomLevel;

  // Initialize the D3 simulation, nodes, links and zoom behavior.
  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl || width <= 0 || height <= 0) return undefined;

    const svg = d3.select(svgEl);
    svg.selectAll('*').remove();

    const nodes: SimNode[] = data.nodes.map((n) => ({ ...n }));
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    const links: SimLink[] = [];

    for (const e of data.edges) {
      const source = nodeById.get(e.source);
      const target = nodeById.get(e.target);
      if (source && target) {
        links.push({ source, target, similarity: e.similarity });
      }
    }

    const g = svg.append('g');
    const labelsLayer = g.append('g');

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 4])
      // Wheel zooms the canvas without scrolling the page; drags with
      // other mouse buttons are ignored.
      .filter((event) => {
        if (event.type === 'wheel') return true;
        return event.button === 0;
      })
      .wheelDelta((event) => {
        // Dampen trackpad/mouse wheel zoom intensity.
        const dy = event.deltaY;
        const mode = event.deltaMode; // 0=pixel, 1=line, 2=page
        const normalized = mode === 1 ? dy * 16 : mode === 2 ? dy * height : dy;
        return -normalized * 0.0012;
      })
      .on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        g.attr('transform', event.transform.toString());
        setZoomLevelRef.current(event.transform.k);
        labelsLayer.selectAll('text').style('opacity', event.transform.k > 0.75 ? 1 : 0);
      });

    svg.call(zoom).on('dblclick.zoom', null);
    zoomRef.current = zoom;

    const mode: GraphLayoutMode = layoutMode || 'force';
    if (mode === 'tree') {
      applyTreeLayout(nodes, links, width, height);
    } else if (mode === 'radial') {
      applyRadialLayout(nodes, links, width, height);
    }

    const simulation =
      mode === 'force'
        ? d3
            .forceSimulation(nodes)
            .force(
              'link',
              d3
                .forceLink<SimNode, SimLink>(links)
                .id((d: SimNode) => d.id)
                .distance(FORCE_CONFIG.linkDistance)
            )
            .force('charge', d3.forceManyBody().strength(FORCE_CONFIG.chargeStrength))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collide', d3.forceCollide(FORCE_CONFIG.collideRadius))
        : d3.forceSimulation(nodes).stop();

    const dragBehavior = d3
      .drag<SVGCircleElement, SimNode>()
      .on('start', (event: D3DragEvent<SVGCircleElement, SimNode, SimNode>, d: SimNode) => {
        if (mode !== 'force') return;
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
      })
      .on('drag', (event: D3DragEvent<SVGCircleElement, SimNode, SimNode>, d: SimNode) => {
        d.fx = event.x;
        d.fy = event.y;
        if (mode !== 'force') {
          d.x = event.x;
          d.y = event.y;
        }
      })
      .on('end', (event: D3DragEvent<SVGCircleElement, SimNode, SimNode>, d: SimNode) => {
        if (mode !== 'force') return;
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
      });

    const link = g
      .append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', 'var(--text-300)')
      .attr('stroke-opacity', (d: SimLink) => 0.1 + d.similarity * 0.7);

    const node = g
      .append('g')
      .selectAll<SVGCircleElement, SimNode>('circle')
      .data(nodes)
      .join('circle')
      .attr('data-testid', 'graph-node')
      .attr('r', (d: SimNode) => Math.min(20, Math.max(4, Math.log2(d.stars + 1) * 2 + 4)))
      .attr('fill', (d: SimNode) => `var(--chart-${colorIndexForId(d.id)})`)
      .attr('stroke', 'transparent')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('click', (_e: MouseEvent, d: SimNode) => onNodeClickRef.current(d))
      .on('dblclick', (_e: MouseEvent, d: SimNode) => onNodeDoubleClickRef.current(d))
      .call(dragBehavior);

    const labels = labelsLayer
      .selectAll<SVGTextElement, SimNode>('text')
      .data(nodes)
      .join('text')
      .text((d: SimNode) => d.name.split('/')[1] ?? d.name)
      .attr('font-size', 10)
      .attr('fill', 'var(--text-600)')
      .attr('text-anchor', 'middle')
      .attr('dy', -14)
      .style('pointer-events', 'none')
      .style('opacity', 0);

    const paint = () => {
      link
        .attr('x1', (d: SimLink) => (d.source as SimNode).x ?? 0)
        .attr('y1', (d: SimLink) => (d.source as SimNode).y ?? 0)
        .attr('x2', (d: SimLink) => (d.target as SimNode).x ?? 0)
        .attr('y2', (d: SimLink) => (d.target as SimNode).y ?? 0);
      node.attr('cx', (d: SimNode) => d.x ?? 0).attr('cy', (d: SimNode) => d.y ?? 0);
      labels.attr('x', (d: SimNode) => d.x ?? 0).attr('y', (d: SimNode) => d.y ?? 0);
    };

    if (mode === 'force') {
      simulation.on('tick', paint);
    } else {
      paint();
    }

    return () => {
      simulation.stop();
      svg.on('.zoom', null);
      svg.selectAll('*').remove();
    };
  }, [data, width, height, layoutMode]);

  // Respond to zoom requests coming from GraphControls.
  useEffect(() => {
    const svgEl = svgRef.current;
    const zoom = zoomRef.current;
    if (!svgEl || !zoom || !zoomDirection) return;
    const svg = d3.select(svgEl);
    const factor = zoomDirection === 'in' ? 1.2 : 1 / 1.2;
    svg.transition().duration(200).call(zoom.scaleBy, factor);
  }, [zoomDirection, zoomTick]);

  // Update only the selection/highlight strokes; the simulation is not rebuilt.
  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    d3.select(svgEl)
      .selectAll<SVGCircleElement, SimNode>('circle[data-testid="graph-node"]')
      .attr('stroke', (d: SimNode) =>
        d.id === selectedNodeId || d.id === highlightNodeId ? 'var(--brand-500)' : 'transparent'
      );
  }, [selectedNodeId, highlightNodeId]);

  return (
    <svg
      ref={svgRef}
      width={width}
      height={height}
      className="graph-svg force-graph-svg"
      data-testid="force-graph-svg"
    />
  );
}
