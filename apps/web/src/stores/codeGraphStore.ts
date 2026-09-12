/**
 * @file codeGraphStore.ts
 * @description UI state for the code-graph page: filters, display toggles, node
 * budget, selection, search query, view mode and panel collapse flags.
 *
 * Responsibilities:
 * - Hold node/edge type filters and display toggles (labels, dead code,
 *   status coloring, test/entry-point hiding) plus the node budget
 * - Keep the node selection, search query, view mode, and panel collapse
 *   flag for the code-graph page
 * - Toggle node types between null (= all) and an explicit set, collapsing
 *   the empty set back to null
 */
import { create } from 'zustand';
import type { CodeGraphNode } from '@/components/code-graph/types';

interface CodeGraphState {
  nodeTypeFilter: Set<string> | null; // null = all
  edgeTypeFilter: Set<string> | null;
  showLabels: boolean;
  showOnlyDead: boolean;
  colorByStatus: boolean;
  hideTests: boolean;
  hideEntryPoints: boolean;
  nodeBudget: number;
  selectedNode: CodeGraphNode | null;
  searchQuery: string;
  viewMode: 'structure' | 'cluster' | 'trace';
  /** Whether the left filter panel is collapsed */
  leftPanelCollapsed: boolean;
  setNodeTypeFilter: (v: Set<string> | null) => void;
  toggleNodeType: (kind: string) => void;
  setEdgeTypeFilter: (v: Set<string> | null) => void;
  setShowLabels: (v: boolean) => void;
  setShowOnlyDead: (v: boolean) => void;
  setColorByStatus: (v: boolean) => void;
  setHideTests: (v: boolean) => void;
  setHideEntryPoints: (v: boolean) => void;
  setNodeBudget: (v: number) => void;
  selectNode: (n: CodeGraphNode | null) => void;
  setSearchQuery: (q: string) => void;
  setViewMode: (m: CodeGraphState['viewMode']) => void;
  setLeftPanelCollapsed: (collapsed: boolean) => void;
}

export const useCodeGraphStore = create<CodeGraphState>((set, get) => ({
  nodeTypeFilter: null,
  edgeTypeFilter: null,
  showLabels: false,
  showOnlyDead: false,
  colorByStatus: false,
  hideTests: false,
  hideEntryPoints: false,
  nodeBudget: 5000,
  selectedNode: null,
  searchQuery: '',
  viewMode: 'structure',
  leftPanelCollapsed: false,
  setNodeTypeFilter: (v) => set({ nodeTypeFilter: v }),
  toggleNodeType: (kind) => {
    const cur = get().nodeTypeFilter;
    if (!cur) {
      set({ nodeTypeFilter: new Set([kind]) });
      return;
    }
    const next = new Set(cur);
    if (next.has(kind)) next.delete(kind);
    else next.add(kind);
    set({ nodeTypeFilter: next.size ? next : null });
  },
  setEdgeTypeFilter: (v) => set({ edgeTypeFilter: v }),
  setShowLabels: (v) => set({ showLabels: v }),
  setShowOnlyDead: (v) => set({ showOnlyDead: v }),
  setColorByStatus: (v) => set({ colorByStatus: v }),
  setHideTests: (v) => set({ hideTests: v }),
  setHideEntryPoints: (v) => set({ hideEntryPoints: v }),
  setNodeBudget: (v) => set({ nodeBudget: v }),
  selectNode: (n) => set({ selectedNode: n }),
  setSearchQuery: (q) => set({ searchQuery: q }),
  setViewMode: (m) => set({ viewMode: m }),
  setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
}));
