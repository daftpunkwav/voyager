/**
 * @file useGraphMutations
 * @description Indexing-related mutations triggered from the graph page: batch L1 code indexing and L0 relation-analysis enqueueing.
 *
 * Extracted from GraphPage. Toast messaging and cache invalidation mirror the
 * original implementation. Post-success UI cleanup (closing the panel and
 * clearing selections) is injected by the page so the hook never holds page
 * state.
 *
 * Responsibilities:
 * - Batch L1 code indexing with a queued/failed toast report
 * - L0 relation-analysis enqueueing with success/error toasts
 * - Invalidate the global index-status queries after either mutation
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { batchIndexCodeGraph } from '@/api/codeGraph';
import { enqueueL0 } from '@/api/graph';
import { useUIStore } from '@/stores/uiStore';

export function useGraphMutations(onBatchIndexed: () => void) {
  const addToast = useUIStore((s) => s.addToast);
  const { t } = useTranslation('graph');
  const queryClient = useQueryClient();

  const batchIndex = useMutation({
    mutationFn: (ids: string[]) => batchIndexCodeGraph(ids),
    // api/codeGraph.batchIndexCodeGraph resolves each repo's clone path and
    // enqueues one job per id; it answers {queued, failed} project ids
    onSuccess: (payload) => {
      const queuedLen = payload.queued.length;
      const failedLen = payload.failed.length;
      addToast({
        type: failedLen === 0 ? 'success' : 'warning',
        message:
          t('graph:toast.batchQueued', { queued: queuedLen }) +
          (failedLen ? t('graph:toast.batchFailedSuffix', { failed: failedLen }) : ''),
      });
      onBatchIndexed();
      void queryClient.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: () => addToast({ type: 'error', message: t('graph:toast.batchIndexFailed') }),
  });

  const analyzeL0 = useMutation({
    mutationFn: (kinds: string[]) => enqueueL0(kinds),
    onSuccess: () => {
      addToast({ type: 'success', message: t('graph:toast.l0Queued') });
      void queryClient.invalidateQueries({ queryKey: ['graph-index-statuses'] });
    },
    onError: (e) =>
      addToast({
        type: 'error',
        message: e instanceof Error ? e.message : t('graph:toast.l0RequestFailed'),
      }),
  });

  return { batchIndex, analyzeL0 };
}
