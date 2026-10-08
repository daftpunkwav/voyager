/**
 * @file ProjectCodeGraphCard
 * @description Project detail sidebar card for the code-graph index: status badge, trigger/delete, and a link to the graph page.
 *
 * Responsibilities:
 * - Poll and display the project index status via the code-graph hooks
 * - Trigger indexing and delete the index, reporting failures as localized
 *   toasts
 * - Link to the code-graph page once the index is ready
 *
 * The backend enqueue_index has no index-mode parameter, so there is one
 * trigger action instead of a fast/moderate/full selector.
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useDeleteIndex, useIndexStatus, useTriggerIndex } from '@/hooks/useCodeGraph';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';
import { routes } from '@/utils/routes';

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

/** Shows index status; supports triggering or deleting the index, and links to the graph page once ready */
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
          [{status?.status}] {(status?.error?.trim() ?? '') || t('sources:graph.failedFallback')}
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
          {statusQ.error?.message || t('sources:checkBackend')}
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
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={isBusy || trigger.isPending || delIndex.isPending}
            onClick={() => trigger.mutate()}
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
              onClick={() => {
                void (async () => {
                  if (
                    await confirmDialog({ message: t('sources:graph.deleteConfirm'), danger: true })
                  ) {
                    delIndex.mutate();
                  }
                })();
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
