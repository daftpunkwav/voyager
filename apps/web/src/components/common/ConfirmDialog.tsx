/**
 * @file ConfirmDialog
 * @description Generic confirmation dialog rendered through the shared
 * ModalOverlay (portal + scrim + enter/exit animation).
 *
 * Responsibilities:
 * - Resolve default button labels through i18n at render time
 * - Cancel on Escape or overlay click while open
 */
import { useTranslation } from 'react-i18next';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  danger,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // Defaults resolve through i18n at render time (hook values cannot be default params).
  const { t } = useTranslation('common');
  const confirmText = confirmLabel ?? t('common:dialog.confirm');
  const cancelText = cancelLabel ?? t('common:action.cancel');

  return (
    <ModalOverlay open={open} onClose={onCancel}>
      <div
        className="modal glass-card glass-card--dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="confirm-title" className="modal__title">
          {title}
        </h3>
        <p className="modal__message">{message}</p>
        <div className="modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            {cancelText}
          </button>
          <button
            type="button"
            className={danger ? 'btn btn-danger' : 'btn btn-primary'}
            onClick={onConfirm}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
