/**
 * @file graphStore.ts
 * @description UI state for the L0 graph page: node selection/highlight, search,
 * similarity/edge filters, kind filter, view and layout modes, panel collapse
 * flags and zoom control.
 *
 * Responsibilities:
 * - Hold L0 view selections: node selection/highlight, search, similarity
 *   and edge-type filters, and the resource-kind filter
 * - Keep view/layout modes, panel collapse flags, and zoom requests
 *   (tick-based so repeated presses re-trigger the canvas)
 * - Clamp similarity/edge bounds and collapse all/none kind selections back
 *   to null to avoid an empty-set dead graph
 *
 * This module must not depend on UI-layer components.
 */
import { create } from 'zustand';

/** L0 graph view mode (presentation form). */
export type GraphViewMode = 'force' | 'list';

/** Geometric layout inside the L0 force canvas (mirrors the native engine's force/tree/radial). */
export type GraphLayoutMode = 'force' | 'tree' | 'radial';

interface GraphState {
  selectedNodeId: string | null;
  highlightNodeId: string | null;
  searchQuery: string;
  minSimilarity: number;
  maxEdges: number;
  /** L0 resource-kind filter: null = all; otherwise the selected kind set (repo/doc/web) */
  kindsFilter: Set<string> | null;
  /** L0 edge type: related | cross_repo | all */
  edgeTypeFilter: string | null;
  /** L0 view mode */
  viewMode: GraphViewMode;
  /** Force-canvas layout algorithm */
  layoutMode: GraphLayoutMode;
  /** Whether the left info panel is collapsed */
  leftPanelCollapsed: boolean;
  /** Whether the node detail panel is collapsed */
  detailCollapsed: boolean;
  zoomLevel: number;
  zoomTick: number;
  zoomDirection: 'in' | 'out' | null;
  selectNode: (nodeId: string | null) => void;
  highlightNode: (nodeId: string | null) => void;
  setSearchQuery: (query: string) => void;
  setMinSimilarity: (value: number) => void;
  setMaxEdges: (value: number) => void;
  toggleKindFilter: (kind: string) => void;
  setKindsFilter: (kinds: Set<string> | null) => void;
  setEdgeTypeFilter: (edgeType: string | null) => void;
  setViewMode: (mode: GraphViewMode) => void;
  setLayoutMode: (mode: GraphLayoutMode) => void;
  setLeftPanelCollapsed: (collapsed: boolean) => void;
  setDetailCollapsed: (collapsed: boolean) => void;
  setZoomLevel: (level: number) => void;
  requestZoom: (direction: 'in' | 'out') => void;
  resetView: () => void;
}

export const useGraphStore = create<GraphState>((set) => ({
  selectedNodeId: null,
  highlightNodeId: null,
  searchQuery: '',
  minSimilarity: 0.08,
  /** Aligned with the API's query `le` bound; larger values cause a 422 validation error against a not-yet-updated backend. */
  maxEdges: 1000,
  kindsFilter: null,
  edgeTypeFilter: null,
  viewMode: 'force',
  layoutMode: 'force',
  leftPanelCollapsed: false,
  detailCollapsed: false,
  zoomLevel: 1.0,
  zoomTick: 0,
  zoomDirection: null,

  selectNode: (nodeId) => set({ selectedNodeId: nodeId, detailCollapsed: false }),
  highlightNode: (nodeId) => set({ highlightNodeId: nodeId }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setMinSimilarity: (value) => set({ minSimilarity: Math.max(0, Math.min(1, value)) }),
  setMaxEdges: (value) => set({ maxEdges: Math.max(10, Math.min(1000, value)) }),
  toggleKindFilter: (kind) =>
    set((state) => {
      const base = state.kindsFilter ?? new Set(['repo', 'doc', 'web']);
      const next = new Set(base);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      // All/none both collapse back to null (= all), avoiding an empty-set dead graph
      return { kindsFilter: next.size === 0 || next.size === 3 ? null : next };
    }),
  setKindsFilter: (kinds) => set({ kindsFilter: kinds }),
  setEdgeTypeFilter: (edgeType) => set({ edgeTypeFilter: edgeType }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setLayoutMode: (mode) => set({ layoutMode: mode }),
  setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
  setDetailCollapsed: (collapsed) => set({ detailCollapsed: collapsed }),
  setZoomLevel: (level) => set({ zoomLevel: level }),
  requestZoom: (direction) =>
    set((state) => ({ zoomDirection: direction, zoomTick: state.zoomTick + 1 })),

  resetView: () =>
    set({
      selectedNodeId: null,
      highlightNodeId: null,
      searchQuery: '',
      zoomLevel: 1.0,
      layoutMode: 'force',
    }),
}));
