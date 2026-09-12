/**
 * @file GraphPage
 * @description Coordination page for the graph (universe) view: data orchestration plus layout assembly.
 *
 * Indexing mutations live in useGraphMutations.ts and toolbar height syncing
 * in useToolbarHeightSync.ts; the batch panel, list view, and node detail
 * (with similar pagination) are sibling controlled subcomponents. This file
 * keeps state orchestration, derived data, and branch layouts only. The page
 * probe snapshot (rememberGraphSnapshot) is still written here.
 *
 * Responsibilities:
 * - Orchestrate L0 graph data: apply similarity/edge filters, derive the
 *   search highlight, and keep the filtered node/edge set
 * - Assemble the branch layouts (force canvas vs. list), the toolbar, the
 *   batch panel, and the node detail panel
 * - Centralize navigation callbacks and post-index cleanup for the
 *   sibling subcomponents
 * - Publish the current view's counts and selection to the page probe
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useGraph } from '@/hooks/useGraph';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphViewMode } from '@/stores/graphStore';
import { useUIStore } from '@/stores/uiStore';
import { UniverseGraphView } from '@/components/graph/UniverseGraphView';
import { GraphControls } from '@/components/graph/GraphControls';
import { GraphGuidePanel } from '@/components/graph/GraphGuidePanel';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { routes } from '@/utils/routes';
import { backendUnreachable } from '@/utils/errors';
import type { GraphNode } from '@/api/types';
import { rememberGraphSnapshot } from './provider';
import { VIEW_MODES } from './graphConstants';
import { useGraphMutations } from './useGraphMutations';
import { useToolbarHeightSync } from './useToolbarHeightSync';
import { GraphBatchPanel } from './GraphBatchPanel';
import { GraphListView } from './GraphListView';
import { GraphNodeDetail } from './GraphNodeDetail';

export function GraphPage() {
  const { t } = useTranslation('graph');
  const { data, isLoading, isError, error, refetch } = useGraph();
  const containerRef = useRef<HTMLDivElement>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchSelected, setBatchSelected] = useState<Set<string>>(new Set());
  const [cameraResetTick, setCameraResetTick] = useState(0);
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const selectNode = useGraphStore((s) => s.selectNode);
  const highlightNode = useGraphStore((s) => s.highlightNode);
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const edgeTypeFilter = useGraphStore((s) => s.edgeTypeFilter);
  const minSimilarity = useGraphStore((s) => s.minSimilarity);
  const viewModeRaw = useGraphStore((s) => s.viewMode);
  /** Legacy cluster/edges modes are normalized to the universe graph or the list. */
  const viewMode: GraphViewMode = viewModeRaw === 'list' ? 'list' : 'force';
  const setViewMode = useGraphStore((s) => s.setViewMode);
  const leftPanelCollapsed = useGraphStore((s) => s.leftPanelCollapsed);
  const addToast = useUIStore((s) => s.addToast);
  const navigate = useNavigate();
  const showUniverseChrome = viewMode === 'force';

  // UI cleanup after a successful batch index (close panel + clear selection), same timing as before the extraction
  const { batchIndex, analyzeL0 } = useGraphMutations(() => {
    setBatchOpen(false);
    setBatchSelected(new Set());
  });

  // L0 relation-analysis scope: no filter = all kinds; filter active = selected kinds only
  const analyzeKinds = kindsFilter ? [...kindsFilter].sort() : ['repo', 'doc', 'web'];

  const filteredData = useMemo(() => {
    let nodes = data?.nodes ?? [];
    let edges = data?.edges ?? [];
    if (minSimilarity > 0) {
      edges = edges.filter((e) => e.similarity >= minSimilarity);
    }
    const ids = new Set(nodes.map((n) => n.id));
    edges = edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    if (edgeTypeFilter) {
      edges = edges.filter((e) => (e.edge_type || 'related') === edgeTypeFilter);
    }
    return { nodes, edges };
  }, [data, minSimilarity, edgeTypeFilter]);

  useEffect(() => {
    if (!searchQuery || !data) {
      highlightNode(null);
      return;
    }
    const q = searchQuery.toLowerCase();
    const match = data.nodes.find((n) => n.name.toLowerCase().includes(q));
    highlightNode(match?.id ?? null);
  }, [searchQuery, data, highlightNode]);

  const selectedNode = filteredData.nodes.find((n) => n.id === selectedNodeId);

  // Publish the current view's node/edge counts to the page probe provider; clear to null while data is missing instead of fabricating numbers
  useEffect(() => {
    if (!data) {
      rememberGraphSnapshot(null);
      return;
    }
    rememberGraphSnapshot({
      nodes: filteredData.nodes.length,
      edges: filteredData.edges.length,
      selectedId: selectedNodeId ?? '',
      selectedName: selectedNode?.name ?? '',
    });
  }, [data, filteredData, selectedNodeId, selectedNode]);

  // Align the right detail panel height with the left info panel (observation and dependency timing handled by the hook)
  useToolbarHeightSync(containerRef, {
    viewMode,
    leftPanelCollapsed,
    batchOpen,
    isLoading,
    nodeCount: data?.nodes.length,
  });

  if (isLoading) {
    return (
      <div className="graph-page-shell page-scaffold">
        <LoadingSpinner fullScreen label={t('graph:page.loading')} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="graph-page-shell page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title={t('graph:page.loadFailedTitle')}
            description={error instanceof Error ? error.message : backendUnreachable()}
            icon={EmptyStateIcons.graph}
            onRetry={() => void refetch()}
          />
        </div>
      </div>
    );
  }

  if ((data?.nodes.length ?? 0) < 2) {
    return (
      <div className="graph-page-shell page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title={t('graph:page.emptyTitle')}
            description={t('graph:page.emptyDescription')}
            icon={EmptyStateIcons.graph}
            action={
              <button
                type="button"
                className="btn btn-primary"
                disabled={analyzeL0.isPending}
                onClick={() => analyzeL0.mutate(analyzeKinds)}
              >
                {analyzeL0.isPending ? t('graph:batch.submitting') : t('graph:batch.analyze')}
              </button>
            }
          />
        </div>
      </div>
    );
  }

  /** Batch L1 code indexing only applies to repo resources. */
  const repoNodes = filteredData.nodes.filter((n) => !n.kind || n.kind === 'repo');

  // Navigation actions shared by the detail panel and the list (navigate is centralized in this page)
  const openResource = (n: GraphNode) => navigate(routes.sourceOf(n.kind, n.resourceId ?? n.id));
  const openCodeGraph = (n: GraphNode) => navigate(routes.codeGraph(n.resourceId ?? n.id));

  const batchSlot = (
    <GraphBatchPanel
      open={batchOpen}
      onToggle={() => setBatchOpen((v) => !v)}
      onClose={() => setBatchOpen(false)}
      analyzeKinds={analyzeKinds}
      analyzePending={analyzeL0.isPending}
      onAnalyze={() => analyzeL0.mutate(analyzeKinds)}
      repoNodes={repoNodes}
      selected={batchSelected}
      onSelectedChange={setBatchSelected}
      indexPending={batchIndex.isPending}
      onIndex={() => batchIndex.mutate([...batchSelected])}
      showCameraReset={showUniverseChrome}
      onCameraReset={() => setCameraResetTick((n) => n + 1)}
    />
  );

  return (
    <div className="graph-page-shell">
      <div className="graph-content">
        <div
          className={`graph-stage${showUniverseChrome ? ' graph-stage--universe' : ' graph-stage--list'}`}
          ref={containerRef}
        >
          <GraphControls
            showLayout={showUniverseChrome}
            viewModes={VIEW_MODES}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            batchSlot={batchSlot}
          />

          {viewMode === 'force' && (
            <UniverseGraphView
              data={filteredData}
              cameraResetTick={cameraResetTick}
              onNodeClick={(n) => selectNode(n.id)}
              onNodeDoubleClick={(n) =>
                navigate(
                  n.kind === 'doc' || n.kind === 'web'
                    ? routes.sourceOf(n.kind, n.resourceId ?? n.id)
                    : routes.codeGraph(n.resourceId ?? n.id)
                )
              }
            />
          )}

          {viewMode === 'list' && (
            <GraphListView
              data={filteredData}
              selectedNodeId={selectedNodeId}
              onSelectNode={selectNode}
              onOpenResource={openResource}
              onOpenCodeGraph={openCodeGraph}
            />
          )}

          {selectedNode && (
            <GraphNodeDetail
              node={selectedNode}
              data={filteredData}
              onClose={() => selectNode(null)}
              onSelectNode={selectNode}
              onOpenResource={openResource}
              onOpenCodeGraph={openCodeGraph}
              onOpenRepo={(n) => navigate(routes.sourceRepo(n.resourceId ?? n.id))}
            />
          )}

          <div className="graph-statusbar glass-card glass-card--overview-inner">
            <div>
              <span className="stat-row">
                <span className="stat-dot" />
                <span className="stat-mono">
                  {t('graph:statusbar.nodesEdges', {
                    nodes: filteredData.nodes.length,
                    edges: filteredData.edges.length,
                  })}
                </span>
              </span>
            </div>
            <div className="export-actions">
              <button
                type="button"
                className="export-btn"
                onClick={() =>
                  addToast({ type: 'info', message: t('graph:toast.exportComingSoon') })
                }
              >
                {t('graph:statusbar.export')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <GraphGuidePanel selectedNodeId={selectedNodeId} />
    </div>
  );
}
