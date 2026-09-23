/**
 * @file ProjectCodeGraphCard
 * @description Project detail sidebar card for the code-graph index: status badge, mode selection, trigger/delete, and a link to the graph page.
 *
 * Responsibilities:
 * - Poll and display the project index status via the code-graph hooks
 * - Trigger indexing in a chosen mode and delete the index, reporting
 *   failures as localized toasts
 * - Link to the code-graph page once the index is ready
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useDeleteIndex, useIndexStatus, useTriggerIndex } from '@/hooks/useCodeGraph';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';
import { routes } from '@/utils/routes';

const INDEX_MODE_KEYS: Record<string, string> = {
  fast: 'sources:graph.mode.fast',
  moderate: 'sources:graph.mode.moderate',
  full: 'sources:graph.mode.full',
};

const INDEX_STATUS_KEYS: Record<string, string> = {
  NONE: 'sources:graph.status.NONE',
  QUEUED: 'sources:graph.status.QUEUED',
  CLONING: 'sources:graph.status.CLONING',
  INDEXING: 'sources:graph.status.INDEXING',
  READY: 'sources:graph.status.READY',
  STALE: 'sources:graph.status.STALE',
  CLONE_FAILED: 'sources:graph.status.CLONE_FAILED',
  INDEX_FAILED: 'sources:graph.status.INDEX_FAILED',
};

/** Shows index status stats; supports choosing a mode to trigger or delete the index, and links to the graph page once ready */
export function CodeGraphIndexCard({ projectId }: { projectId: string }) {
  const { t } = useTranslation('sources');
  const addToast = useUIStore((s) => s.addToast);
  const onIndexOpError = (label: string) => (err: Error) => {
    addToast({
      type: 'error',
      message: t('sources:graph.opFailed', {
        label,
        message: err.message || t('sources:checkBackend'),
      }),
    });
  };
  const statusQ = useIndexStatus(projectId);
  const trigger = useTriggerIndex(projectId, {
    onError: onIndexOpError(t('sources:graph.opTrigger')),
  });
  const delIndex = useDeleteIndex(projectId, {
    onError: onIndexOpError(t('sources:graph.opDelete')),
  });
  const [mode, setMode] = useState<'fast' | 'moderate' | 'full'>('fast');
  const status = statusQ.data;

  const isReady = status?.status === 'READY';
  const isBusy = ['QUEUED', 'CLONING', 'INDEXING'].includes(status?.status ?? '');
  const isFailed = ['CLONE_FAILED', 'INDEX_FAILED'].includes(status?.status ?? '');
  const canDelete = status && status.status !== 'NONE';
  const graphUnavailable = statusQ.isError;

  return (
    <div className={GLASS_OUTER} style={{ marginTop: 12 }}>
      <div className="card-header">
        <div className="card-title">{t('sources:graph.cardTitle')}</div>
        {status && (
          <span
            className={`badge ${isReady ? 'badge--success' : isFailed ? 'badge--error' : isBusy ? 'badge--warn' : ''}`}
            style={{ fontSize: 11 }}
          >
            {INDEX_STATUS_KEYS[status.status] ? t(INDEX_STATUS_KEYS[status.status]) : status.status}
          </span>
        )}
      </div>

      {status && (
        <div style={{ padding: '0 16px 8px', fontSize: 12, color: 'var(--text-500)' }}>
          {status.node_count != null && (
            <span>
              {t('sources:graph.stats', {
                nodes: status.node_count,
                edges: status.edge_count ?? 0,
              })}
            </span>
          )}
          {status.index_mode && (
            <span style={{ marginLeft: 8 }}>
              {t('sources:graph.modeLabel', {
                mode: INDEX_MODE_KEYS[status.index_mode]
                  ? t(INDEX_MODE_KEYS[status.index_mode])
                  : status.index_mode,
              })}
            </span>
          )}
        </div>
      )}

      {isFailed && (
        <div
          style={{
            margin: '0 16px 8px',
            padding: 8,
            background: 'var(--error-bg, rgba(239,68,68,.08))',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--error)',
          }}
        >
          [{status?.status}] {status?.error?.trim() || t('sources:graph.failedFallback')}
        </div>
      )}

      {graphUnavailable && (
        <div
          style={{
            margin: '0 16px 8px',
            padding: 8,
            background: 'var(--error-bg, rgba(239,68,68,.08))',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--error)',
          }}
        >
          {t('sources:graph.unavailablePrefix')}
          {(statusQ.error as Error)?.message || t('sources:checkBackend')}
        </div>
      )}

      {!graphUnavailable && (
        <div
          style={{
            padding: '0 16px 12px',
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          <select
            className="field input"
            style={{ height: 28, fontSize: 12, flex: '0 0 auto', minWidth: 72 }}
            value={mode}
            disabled={isBusy || trigger.isPending || delIndex.isPending}
            onChange={(e) => setMode(e.target.value as 'fast' | 'moderate' | 'full')}
          >
            <option value="fast">{t('sources:graph.mode.fast')}</option>
            <option value="moderate">{t('sources:graph.modeOption.moderate')}</option>
            <option value="full">{t('sources:graph.mode.full')}</option>
          </select>

          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={isBusy || trigger.isPending || delIndex.isPending}
            onClick={() => trigger.mutate(mode)}
            style={{ height: 28, fontSize: 12 }}
          >
            {isBusy
              ? t('sources:graph.btnIndexing')
              : status?.status === 'NONE' || !status
                ? t('sources:graph.btnStart')
                : t('sources:graph.btnReindex')}
          </button>

          {canDelete && (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={isBusy || trigger.isPending || delIndex.isPending}
              style={{ height: 28, fontSize: 12, color: '#dc2626' }}
              onClick={async () => {
                if (
                  await confirmDialog({ message: t('sources:graph.deleteConfirm'), danger: true })
                ) {
                  delIndex.mutate();
                }
              }}
            >
              {t('sources:graph.opDelete')}
            </button>
          )}

          {isReady && (
            <Link
              to={routes.codeGraph(projectId)}
              className={`btn btn-sm ${GLASS_INNER}`}
              style={{ height: 28, fontSize: 12 }}
            >
              {t('sources:graph.viewGraph')}
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
