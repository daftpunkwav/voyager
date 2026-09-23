/**
 * @file ConfirmDialogHost
 * @description Shell-mounted host for the imperative confirm dialog: renders
 * the active uiStore confirm request through the shared ConfirmDialog. Callers
 * use `confirmDialog(...)` (Promise of boolean) instead of window.confirm, so
 * destructive actions get the same glass dialog as everything else.
 */

import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';

export function ConfirmDialogHost() {
  const { t } = useTranslation('common');
  const request = useUIStore((s) => s.confirmRequest);
  const resolveConfirm = useUIStore((s) => s.resolveConfirm);

  return (
    <ConfirmDialog
      open={request !== null}
      title={request?.title ?? t('common:dialog.title')}
      message={request?.message ?? ''}
      confirmLabel={request?.confirmLabel}
      cancelLabel={request?.cancelLabel}
      danger={request?.danger}
      onConfirm={() => resolveConfirm(true)}
      onCancel={() => resolveConfirm(false)}
    />
  );
}
