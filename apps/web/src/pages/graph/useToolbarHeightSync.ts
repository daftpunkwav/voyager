/**
 * @file useToolbarHeightSync
 * @description Measures .graph-toolbar and writes its height into a CSS variable on the stage element.
 *
 * Keeps the right detail panel and the left info panel aligned; the last
 * expanded height is retained while the left panel is collapsed. The observed
 * target, CSS variable name, and re-run triggers match the original
 * implementation in GraphPage.
 *
 * Responsibilities:
 * - Measure the .graph-toolbar height and write it into the stage CSS
 *   variable via a ResizeObserver
 * - Re-run on view mode, panel collapse, batch panel, loading, and data
 *   changes; skip while the toolbar is collapsed
 */

import { useEffect } from 'react';
import type { RefObject } from 'react';
import type { GraphViewMode } from '@/stores/graphStore';

interface ToolbarHeightSyncDeps {
  viewMode: GraphViewMode;
  leftPanelCollapsed: boolean;
  batchOpen: boolean;
  isLoading: boolean;
  /** Current data node count (i.e. data?.nodes.length; undefined = data not loaded yet) */
  nodeCount: number | undefined;
}

export function useToolbarHeightSync(
  stageRef: RefObject<HTMLDivElement | null>,
  deps: ToolbarHeightSyncDeps
): void {
  const { viewMode, leftPanelCollapsed, batchOpen, isLoading, nodeCount } = deps;

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const toolbar = stage.querySelector('.graph-toolbar');
    if (!(toolbar instanceof HTMLElement)) return;

    const syncHeight = () => {
      if (toolbar.classList.contains('is-collapsed')) return;
      const h = Math.round(toolbar.getBoundingClientRect().height);
      if (h > 0) stage.style.setProperty('--graph-left-panel-h', `${h}px`);
    };

    syncHeight();
    const ro = new ResizeObserver(syncHeight);
    ro.observe(toolbar);
    return () => ro.disconnect();
  }, [stageRef, viewMode, leftPanelCollapsed, batchOpen, isLoading, nodeCount]);
}
