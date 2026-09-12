/**
 * @file IndexStatusBar
 * @description Index status bar embedded in the sidebar: status pill, node
 * budget control, and refresh / fast / standard / full index actions.
 *
 * Responsibilities:
 * - Render the status pill with node budget and refresh / fast / standard / full actions
 * - Resolve status ids to translated labels, rendering unknown ids as-is
 */
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import type { GraphIndexStatus } from './types';

/** Status ids mapped to codeGraph:indexStatus.* label keys; unknown ids render as-is. */
const STATUS_KEY: Record<string, string> = {
  NONE: 'codeGraph:indexStatus.NONE',
  QUEUED: 'codeGraph:indexStatus.QUEUED',
  CLONING: 'codeGraph:indexStatus.CLONING',
  INDEXING: 'codeGraph:indexStatus.INDEXING',
  READY: 'codeGraph:indexStatus.READY',
  STALE: 'codeGraph:indexStatus.STALE',
  CLONE_FAILED: 'codeGraph:indexStatus.CLONE_FAILED',
  INDEX_FAILED: 'codeGraph:indexStatus.INDEX_FAILED',
};

/** Resolve a status id to its codeGraph:indexStatus.* label; unknown ids render as-is. */
function statusLabel(t: TFunction, st: string): string {
  const key = STATUS_KEY[st];
  return key ? t(key) : st;
}

type IndexMode = 'fast' | 'moderate' | 'full';

interface Props {
  status?: GraphIndexStatus;
  loading?: boolean;
  onIndex: (mode: IndexMode) => void;
  onRefresh: (mode: IndexMode) => void;
  onDelete?: () => void;
  nodeBudget: number;
  onBudgetChange: (n: number) => void;
  totalNodes?: number | null;
  shownNodes?: number;
  shownEdges?: number;
}

/** Index status for the graph, embedded in the floating left sidebar. */
export function IndexStatusBar({
  status,
  loading,
  onIndex,
  onRefresh,
  onDelete,
  nodeBudget,
  onBudgetChange,
  totalNodes,
  shownNodes,
  shownEdges,
}: Props) {
  const { t } = useTranslation('codeGraph');
  const st = status?.status ?? 'NONE';
  const statsText =
    totalNodes != null && shownNodes != null && totalNodes > shownNodes
      ? t('codeGraph:stats.nodesOfTotal', {
          shown: shownNodes.toLocaleString(),
          total: totalNodes.toLocaleString(),
        })
      : shownNodes != null
        ? t('codeGraph:stats.nodes', { nodes: shownNodes.toLocaleString() }) +
          (shownEdges != null
            ? t('codeGraph:stats.edgesSuffix', { edges: shownEdges.toLocaleString() })
            : '')
        : null;

  const errorText =
    status?.error?.trim() ||
    (st === 'CLONE_FAILED' || st === 'INDEX_FAILED'
      ? t('codeGraph:statusBar.indexFailedRetry')
      : null);

  const canDelete = st !== 'NONE' && Boolean(onDelete);

  return (
    <div className="code-graph-statusbar code-graph-statusbar--inline">
      <div className="code-graph-statusbar__row">
        <span className={`status-pill status-pill--${st.toLowerCase()}`}>{statusLabel(t, st)}</span>
        {status?.index_mode && (
          <span className="muted">
            {t('codeGraph:statusBar.mode', { mode: status.index_mode })}
          </span>
        )}
      </div>
      {errorText && <p className="error">{errorText}</p>}
      <div className="code-graph-statusbar__row code-graph-statusbar__budget">
        {statsText && <span className="code-graph-statusbar__stats">{statsText}</span>}
        <label className="code-graph-statusbar__limit">
          {t('codeGraph:statusBar.limit')}
          <input
            type="number"
            min={1000}
            step={1000}
            value={nodeBudget}
            onChange={(e) => onBudgetChange(Number(e.target.value) || 5000)}
          />
        </label>
      </div>
      <div className="code-graph-statusbar__row code-graph-statusbar__actions">
        {(st === 'READY' || st === 'STALE') && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={loading}
            onClick={() => onRefresh('fast')}
            title={t('codeGraph:statusBar.refreshTitle')}
          >
            {t('codeGraph:statusBar.refresh')}
          </button>
        )}
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={loading}
          onClick={() => onIndex('fast')}
        >
          {t('codeGraph:indexMode.fast')}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={loading}
          onClick={() => onIndex('moderate')}
        >
          {t('codeGraph:indexMode.moderate')}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={loading}
          onClick={() => onIndex('full')}
        >
          {t('codeGraph:indexMode.full')}
        </button>
        {canDelete && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={loading}
            onClick={onDelete}
            title={t('codeGraph:statusBar.deleteTitle')}
          >
            {t('codeGraph:action.delete')}
          </button>
        )}
      </div>
    </div>
  );
}
