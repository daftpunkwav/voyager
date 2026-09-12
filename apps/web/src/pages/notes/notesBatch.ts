/**
 * @file notesBatch
 * @description Batch operations on the note list: archive / unarchive / trash / export, with a single consolidated toast report.
 *
 * Responsibilities:
 * - Run batch actions through the notes hook with consolidated success,
 *   partial, and failure toasts
 * - Surface the single export path when exactly one export succeeds
 */

import { i18n } from '@/i18n';
import { useBatchNotes } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

export function useNotesBatch() {
  const batchNotes = useBatchNotes();
  const addToast = useUIStore((s) => s.addToast);

  const runBatch = async (ids: string[], action: 'archive' | 'unarchive' | 'delete' | 'export') => {
    if (!ids.length) return;
    try {
      const res = await batchNotes.mutateAsync({ ids, action });
      const ok = res.count;
      const failed = res.failed.length;
      const exportPath = action === 'export' && failed === 0 ? res.paths?.[0] : undefined;
      addToast({
        type: failed === 0 ? 'success' : failed === ids.length ? 'error' : 'warning',
        message:
          exportPath && (res.paths?.length ?? 0) === 1
            ? i18n.t('notes:exportedPath', { path: exportPath })
            : failed === 0
              ? i18n.t(`notes:batch.done.${action}`, { n: ok })
              : i18n.t(`notes:batch.partial.${action}`, { ok, failed }),
      });
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : i18n.t('notes:batch.failed'),
      });
    }
  };

  return { runBatch, batchPending: batchNotes.isPending };
}
