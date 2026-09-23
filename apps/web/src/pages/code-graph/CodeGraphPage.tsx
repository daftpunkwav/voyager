/**
 * @file CodeGraphPage
 * @description Code graph page: 3D graph visualization with filtering, search, and node details.
 *
 * Loads the indexed graph for a project, applies client-side filters and L1 layout,
 * and drives camera targeting and highlighting for search and selection. Feeds
 * project id and node/edge counts to the page-awareness provider.
 *
 * Responsibilities:
 * - Orchestrate index lifecycle actions (trigger/refresh/delete) with
 *   localized failure toasts and gate graph loading on READY status
 * - Apply client-side filters, status coloring, and the L1 layout to the
 *   fetched subgraph
 * - Drive the 3D scene: camera targeting, search highlighting, and node
 *   selection with its detail panel
 * - Persist display settings locally and publish the snapshot to the page
 *   probe provider
 */
import { useMemo, useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { GraphScene, computeCameraTarget } from '@/components/graph-viz';
import type { CameraTarget, CodeGraphNode } from '@/components/graph-viz';
import { CodeGraphSidebar } from '@/components/code-graph/CodeGraphSidebar';
import { NodeDetailPanel } from '@/components/code-graph/NodeDetailPanel';
import { IndexStatusBar } from '@/components/code-graph/IndexStatusBar';
import { GraphGuidePanel } from '@/components/graph/GraphGuidePanel';
import { DisplaySettingsMenu } from '@/components/code-graph/DisplaySettingsMenu';
import { applyL1Layout, type L1LayoutMode } from '@/components/code-graph/l1Layout';
import {
  useCodeGraph,
  useIndexStatus,
  useTriggerIndex,
  useRefreshIndex,
  useDeleteIndex,
} from '@/hooks/useCodeGraph';
import { useCodeGraphStore } from '@/stores/codeGraphStore';
import { getProject } from '@/api/projects';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { rememberCodeGraphDetail } from './provider';
import {
  loadDisplaySettings,
  saveDisplaySettings,
  withStatusColorDisplay,
  type DisplaySettings,
} from '@/components/code-graph/density';
import { colorForStatus } from '@/components/code-graph/colors';

export function CodeGraphPage() {
  const { id } = useParams<{ id: string }>();
  const { t } = useTranslation('codeGraph');

  const {
    showLabels,
    nodeBudget,
    selectedNode,
    searchQuery,
    nodeTypeFilter,
    edgeTypeFilter,
    showOnlyDead,
    colorByStatus,
    hideTests,
    hideEntryPoints,
    selectNode,
    setNodeBudget,
  } = useCodeGraphStore();

  const [display, setDisplay] = useState<DisplaySettings>(() => loadDisplaySettings());
  const updateDisplay = useCallback((next: DisplaySettings) => {
    setDisplay(next);
    saveDisplaySettings(next);
  }, []);
  const effectiveDisplay = useMemo(
    () => (colorByStatus ? withStatusColorDisplay(display) : display),
    [colorByStatus, display]
  );

  const statusQ = useIndexStatus(id);
  const status = statusQ.data;
  const ready = status?.status === 'READY';

  const addToast = useUIStore((s) => s.addToast);
  /** labelKey is a codeGraph:indexOp.* key; the toast composes "{{label}} failed: {{message}}". */
  const onIndexOpError = (labelKey: string) => (err: Error) => {
    addToast({
      type: 'error',
      message: t('codeGraph:toast.indexOpFailed', {
        label: t(labelKey),
        message: err.message || t('codeGraph:toast.checkBackend'),
      }),
    });
  };
  const trigger = useTriggerIndex(id, { onError: onIndexOpError('codeGraph:indexOp.trigger') });
  const refresh = useRefreshIndex(id, { onError: onIndexOpError('codeGraph:indexOp.refresh') });
  const delIndex = useDeleteIndex(id, { onError: onIndexOpError('codeGraph:indexOp.delete') });

  const graphQ = useCodeGraph(id, { maxNodes: nodeBudget, enabled: Boolean(ready) });

  const projectQ = useQuery({
    queryKey: ['project', id],
    enabled: Boolean(id),
    queryFn: () => {
      if (!id) throw new Error(t('codeGraph:error.missingProjectId'));
      return getProject(id);
    },
  });

  const [cameraTarget, setCameraTarget] = useState<CameraTarget | null>(null);
  const [highlightedIds, setHighlightedIds] = useState<Set<number> | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [layoutMode, setLayoutMode] = useState<L1LayoutMode>('engine');

  const render = graphQ.data?.render;
  const filtered = useMemo(() => {
    if (!render) return null;
    let nodes: CodeGraphNode[] = render.nodes;
    if (nodeTypeFilter) {
      nodes = nodes.filter((n) => nodeTypeFilter.has(n.kind || n.label));
    }
    if (showOnlyDead) nodes = nodes.filter((n) => n.status === 'dead');
    if (hideTests) nodes = nodes.filter((n) => n.status !== 'test');
    if (hideEntryPoints) nodes = nodes.filter((n) => n.status !== 'entry');
    /* Mirror the native engine's deadCodeView: recolor nodes by status, overriding engine star colors */
    if (colorByStatus) {
      nodes = nodes.map((n) => ({
        ...n,
        color: colorForStatus(n.status || ''),
      }));
    }
    const ids = new Set(nodes.map((n) => n.id));
    let edges = render.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
    if (edgeTypeFilter) {
      edges = edges.filter((e) => edgeTypeFilter.has(e.type || e.relation || ''));
    }
    return applyL1Layout({ ...render, nodes, edges }, layoutMode);
  }, [
    render,
    nodeTypeFilter,
    edgeTypeFilter,
    showOnlyDead,
    colorByStatus,
    hideTests,
    hideEntryPoints,
    layoutMode,
  ]);

  // Feed project id and filtered node/edge counts to the page-awareness provider; store null until data arrives instead of fabricating numbers
  useEffect(() => {
    if (!id) {
      rememberCodeGraphDetail(null);
      return;
    }
    rememberCodeGraphDetail({
      projectId: id,
      nodes: filtered ? filtered.nodes.length : null,
      edges: filtered ? filtered.edges.length : null,
    });
  }, [id, filtered]);

  useEffect(() => {
    if (selectedPath) return;
    if (!searchQuery || !filtered) {
      if (!selectedPath) setHighlightedIds(null);
      return;
    }
    const q = searchQuery.toLowerCase();
    const matches = filtered.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        (n.qualified_name || '').toLowerCase().includes(q) ||
        (n.file_path || '').toLowerCase().includes(q)
    );
    const ids = new Set(matches.map((n) => n.id));
    setHighlightedIds(ids.size ? ids : null);
    if (ids.size) setCameraTarget(computeCameraTarget(filtered.nodes, ids));
  }, [searchQuery, filtered, selectedPath]);

  useEffect(() => {
    if (!filtered?.nodes.length) return;
    if (selectedNode || selectedPath) return;
    const ids = new Set(filtered.nodes.map((n) => n.id));
    setCameraTarget(computeCameraTarget(filtered.nodes, ids));
    // Reset the camera only when node count or layout changes, avoiding churn from
    // filtered reference identity changes
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally depend on nodes.length
  }, [filtered?.nodes.length, id, layoutMode, selectedNode, selectedPath]);

  const onSelectPath = (path: string, nodeIds: Set<number>) => {
    if (!path || nodeIds.size === 0) {
      setSelectedPath(null);
      setHighlightedIds(null);
      selectNode(null);
      return;
    }
    setSelectedPath(path);
    setHighlightedIds(nodeIds);
    if (filtered) {
      setCameraTarget(computeCameraTarget(filtered.nodes, nodeIds));
      const candidates = filtered.nodes.filter((n) => nodeIds.has(n.id));
      const prefer =
        candidates.find((n) => (n.kind || n.label) === 'File') ||
        candidates.find((n) => (n.file_path || '') === path) ||
        candidates[0];
      if (prefer) selectNode(prefer);
    }
  };

  const onNodeClick = (node: CodeGraphNode) => {
    selectNode(node);
    if (!filtered) return;
    const neigh = new Set<number>([node.id]);
    for (const e of filtered.edges) {
      if (e.source === node.id) neigh.add(e.target);
      if (e.target === node.id) neigh.add(e.source);
    }
    setHighlightedIds(neigh);
    setCameraTarget(computeCameraTarget(filtered.nodes, new Set([node.id])));
  };

  const projectName = projectQ.data?.name || id;
  const statusSlot = (
    <IndexStatusBar
      status={status}
      loading={statusQ.isLoading || trigger.isPending || refresh.isPending || delIndex.isPending}
      onIndex={(mode) => trigger.mutate(mode)}
      onRefresh={(mode) => refresh.mutate(mode)}
      onDelete={async () => {
        const name = projectQ.data?.name || id || t('codeGraph:delete.fallbackName');
        if (
          await confirmDialog({ message: t('codeGraph:delete.confirm', { name }), danger: true })
        ) {
          delIndex.mutate();
        }
      }}
      nodeBudget={nodeBudget}
      onBudgetChange={setNodeBudget}
      totalNodes={filtered?.total_nodes ?? status?.node_count ?? undefined}
      shownNodes={filtered?.nodes.length}
      shownEdges={filtered?.edges.length}
    />
  );

  return (
    <div className="code-graph-page">
      <div className="code-graph-stage">
        <CodeGraphSidebar
          data={filtered}
          selectedPath={selectedPath}
          onSelectPath={onSelectPath}
          layoutMode={layoutMode}
          onLayoutModeChange={setLayoutMode}
          statusSlot={statusSlot}
        />

        {statusQ.isError && (
          <div
            className="code-graph-empty glass-card glass-card--overview-inner"
            style={{
              border: '1px solid rgba(255,55,95,.28)',
              background: 'var(--error-bg, rgba(239,68,68,.08))',
            }}
          >
            <h2 style={{ color: 'var(--error)' }}>{t('codeGraph:page.serviceUnavailable')}</h2>
            <p>{(statusQ.error as Error)?.message || t('codeGraph:page.statusUnknown')}</p>
          </div>
        )}

        {!ready && !statusQ.isError && (
          <div className="code-graph-empty glass-card glass-card--overview-inner">
            <h2>{t('codeGraph:page.notBuiltTitle')}</h2>
            <p>
              {status?.status === 'CLONE_FAILED' || status?.status === 'INDEX_FAILED'
                ? status.error || t('codeGraph:page.buildFailedFallback')
                : status && ['QUEUED', 'CLONING', 'INDEXING'].includes(status.status)
                  ? t('codeGraph:page.processing', { status: status.status })
                  : t('codeGraph:page.notBuiltHint')}
            </p>
            {(!status ||
              ['NONE', 'CLONE_FAILED', 'INDEX_FAILED', 'STALE'].includes(status.status)) && (
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => trigger.mutate('moderate')}
                disabled={trigger.isPending}
              >
                {t('codeGraph:page.startIndex')}
              </button>
            )}
          </div>
        )}

        {ready && graphQ.isLoading && <LoadingSpinner />}
        {ready && graphQ.isError && (
          <div className="code-graph-empty glass-card glass-card--overview-inner">
            <h2>{t('codeGraph:page.loadFailedTitle')}</h2>
            <p>{(graphQ.error as Error)?.message || t('codeGraph:page.layoutDataUnknown')}</p>
          </div>
        )}
        {ready && filtered && (
          <>
            <div className="code-graph-display-dock">
              <DisplaySettingsMenu settings={display} onChange={updateDisplay} />
            </div>
            <GraphScene
              data={filtered}
              highlightedIds={highlightedIds}
              cameraTarget={cameraTarget}
              showLabels={showLabels}
              enableBloom
              display={effectiveDisplay}
              onNodeClick={onNodeClick}
              onBackgroundClick={() => {
                selectNode(null);
                setHighlightedIds(null);
                setSelectedPath(null);
              }}
            />
          </>
        )}

        {selectedNode && id && (
          <NodeDetailPanel
            node={selectedNode}
            allNodes={filtered?.nodes || []}
            allEdges={filtered?.edges || []}
            projectId={id}
            onClose={() => selectNode(null)}
            onNavigate={onNodeClick}
          />
        )}

        <div className="code-graph-footer glass-card glass-card--overview-inner">
          <span className="stat-row">
            <span className="stat-dot" />
            <span className="stat-mono">
              {filtered
                ? t('codeGraph:statusbar.nodesEdges', {
                    nodes: filtered.nodes.length,
                    edges: filtered.edges.length,
                  })
                : projectName}
            </span>
          </span>
        </div>
      </div>

      <GraphGuidePanel selectedNodeId={id ?? null} />
    </div>
  );
}
