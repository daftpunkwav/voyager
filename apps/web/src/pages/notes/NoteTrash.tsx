/**
 * @file NoteTrash
 * @description Trash dialog in a centered modal: restore, purge, or empty; dangerous confirmations go through ConfirmDialog.
 *
 * Responsibilities:
 * - List trashed notes while the panel is open
 * - Run restore / purge / empty-trash mutations with success and failure
 *   toasts
 * - Gate purge and empty behind explicit confirmations
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useEmptyTrash, usePurgeNote, useRestoreNote, useTrashNotes } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

type Pending = { kind: 'empty' } | { kind: 'purge'; id: string; title: string } | null;

export function TrashPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation('notes');
  const { data: notes = [] } = useTrashNotes(open);
  const restore = useRestoreNote();
  const purge = usePurgeNote();
  const empty = useEmptyTrash();
  const addToast = useUIStore((s) => s.addToast);
  const [pending, setPending] = useState<Pending>(null);

  useEffect(() => {
    if (!open) {
      setPending(null);
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pending) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, pending]);

  if (!open) return null;
  return createPortal(
    <>
      <div className="modal-overlay" role="presentation" onClick={onClose}>
        <aside
          className="modal modal--wide notes-dialog trash-panel glass-card glass-card--dialog"
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-label={t('notes:trash.title')}
        >
          <header className="notes-dialog__head">
            <h3>{t('notes:trash.titleWithCount', { n: notes.length })}</h3>
            <div className="trash-panel__head-actions">
              <button
                type="button"
                className="btn btn-sm btn-danger trash-panel__purge"
                disabled={notes.length === 0 || empty.isPending}
                onClick={() => setPending({ kind: 'empty' })}
              >
                {t('notes:trash.emptyBtn')}
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label={t('notes:close')}
                onClick={onClose}
              >
                ✕
              </button>
            </div>
          </header>
          {notes.length === 0 ? (
            <p className="trash-panel__empty">{t('notes:trash.isEmpty')}</p>
          ) : (
            <ul className="notes-dialog__list">
              {notes.map((n) => (
                <li key={n.id} className="notes-dialog__item">
                  <div className="trash-panel__row">
                    <span className="trash-panel__title">{n.title || t('notes:untitled')}</span>
                    <span className="trash-panel__actions">
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={() =>
                          restore.mutate(n.id, {
                            onSuccess: () =>
                              addToast({ type: 'success', message: t('notes:trash.restored') }),
                          })
                        }
                      >
                        {t('notes:trash.restore')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm bulk-bar__btn--danger"
                        onClick={() =>
                          setPending({
                            kind: 'purge',
                            id: n.id,
                            title: n.title || t('notes:untitled'),
                          })
                        }
                      >
                        {t('notes:trash.purge')}
                      </button>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
      <ConfirmDialog
        open={pending?.kind === 'empty'}
        title={t('notes:trash.emptyConfirmTitle')}
        message={t('notes:trash.emptyConfirmMsg')}
        confirmLabel={t('notes:trash.emptyBtn')}
        danger
        onConfirm={() => {
          empty.mutate(undefined, {
            onSuccess: () => addToast({ type: 'success', message: t('notes:trash.emptyDone') }),
          });
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
      <ConfirmDialog
        open={pending?.kind === 'purge'}
        title={t('notes:trash.purge')}
        message={t('notes:trash.purgeConfirmMsg', {
          title: pending?.kind === 'purge' ? pending.title : '',
        })}
        confirmLabel={t('notes:trash.purge')}
        danger
        onConfirm={() => {
          if (pending?.kind === 'purge') {
            purge.mutate(pending.id, {
              onSuccess: () => addToast({ type: 'success', message: t('notes:trash.purged') }),
            });
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </>,
    document.body
  );
}
