/**
 * @file ConfirmDialogHost
 * @description Shell-mounted host for the imperative confirm dialog: renders
 * the active uiStore confirm request through the shared ConfirmDialog. Callers
 * use `confirmDialog(...)` (Promise of boolean) instead of window.confirm, so
 * destructive actions get the same glass dialog as everything else.
 */

import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';
import type { ConfirmRequest } from '@/stores/uiStore';

export function ConfirmDialogHost() {
  const { t } = useTranslation('common');
  const request = useUIStore((s) => s.confirmRequest);
  const resolveConfirm = useUIStore((s) => s.resolveConfirm);
  // Resolve clears the store request immediately, while ModalOverlay keeps the
  // dialog mounted through its exit animation. Drawing that window from the
  // last request (same pattern as Lightbox's seenSrc) keeps the title/message
  // stable through the fade instead of blanking into the fallback copy.
  const lastRequestRef = useRef<ConfirmRequest | null>(null);
  if (request !== null) lastRequestRef.current = request;
  const shown = request ?? lastRequestRef.current;

  return (
    <ConfirmDialog
      open={request !== null}
      title={shown?.title ?? t('common:dialog.title')}
      message={shown?.message ?? ''}
      confirmLabel={shown?.confirmLabel}
      cancelLabel={shown?.cancelLabel}
      danger={shown?.danger}
      onConfirm={() => resolveConfirm(true)}
      onCancel={() => resolveConfirm(false)}
    />
  );
}
