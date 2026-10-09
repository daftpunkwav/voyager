/**
 * @file readerRemoveFlows
 * @description Confirm-then-delete flows for the source readers (document and
 *  web page): dialog, success toast + back to the sources list, error toast
 *  with the wire message. Kept out of the reader components so those stay
 *  render-only.
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useRemoveDocument, useRemovePage } from '@/hooks/useSources';
import { confirmDialog, useUIStore } from '@/stores/uiStore';

/** Delete a document after confirmation. */
export function useRemoveDocumentFlow() {
  const { t } = useTranslation('sources');
  const navigate = useNavigate();
  const removeDoc = useRemoveDocument();
  const addToast = useUIStore((s) => s.addToast);
  return async (id: string, title: string) => {
    if (
      !(await confirmDialog({
        message: t('sources:doc.deleteConfirm', { title }),
        danger: true,
      }))
    )
      return;
    removeDoc.mutate(id, {
      onSuccess: () => {
        addToast({ type: 'success', message: t('sources:doc.deleted') });
        void navigate('/sources');
      },
      onError: (e) =>
        addToast({
          type: 'error',
          message: e instanceof Error ? e.message : t('sources:deleteFailed'),
        }),
    });
  };
}

/** Delete a web-page clip after confirmation. */
export function useRemovePageFlow() {
  const { t } = useTranslation('sources');
  const navigate = useNavigate();
  const removePage = useRemovePage();
  const addToast = useUIStore((s) => s.addToast);
  return async (id: string, title: string) => {
    if (
      !(await confirmDialog({
        message: t('sources:web.deleteConfirm', { title }),
        danger: true,
      }))
    )
      return;
    removePage.mutate(id, {
      onSuccess: () => {
        addToast({ type: 'success', message: t('sources:web.deleted') });
        void navigate('/sources');
      },
      onError: (e) =>
        addToast({
          type: 'error',
          message: e instanceof Error ? e.message : t('sources:deleteFailed'),
        }),
    });
  };
}
