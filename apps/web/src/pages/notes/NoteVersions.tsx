/**
 * @file NoteVersions
 * @description Version history dialog in a centered liquid-glass modal, sharing the same modal styling as the trash panel.
 *
 * Responsibilities:
 * - List version snapshots (version / time / size) for the current note
 * - Restore a selected version back into the editor via useRestoreVersion
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { formatDateTime } from '@/i18n';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { useNoteVersions, useRestoreVersion } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';

export function VersionPanel({
  noteId,
  open,
  onClose,
}: {
  noteId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation('notes');
  const { data, isLoading } = useNoteVersions(noteId, open);
  const restore = useRestoreVersion();
  const [selected, setSelected] = useState<number | null>(null);
  const addToast = useUIStore((s) => s.addToast);
  useEffect(() => {
    if (!open) setSelected(null);
  }, [open]);
  return (
    <ModalOverlay open={open} onClose={onClose}>
      <aside
        className="modal modal--wide notes-dialog glass-card glass-card--dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={t('notes:versions.title')}
      >
        <header className="notes-dialog__head">
          <h3>{t('notes:versions.title')}</h3>
          <button
            type="button"
            className="icon-btn"
            aria-label={t('notes:close')}
            onClick={onClose}
          >
            ✕
          </button>
        </header>
        {isLoading ? (
          <p className="muted">{t('notes:versions.loading')}</p>
        ) : !data || data.versions.length === 0 ? (
          <p className="muted">{t('notes:versions.empty')}</p>
        ) : (
          <ul className="notes-dialog__list">
            {data.versions.map((v) => (
              <li
                key={v.version}
                className={`notes-dialog__item ${selected === v.version ? 'is-active' : ''}`}
              >
                <button type="button" onClick={() => setSelected(v.version)}>
                  <span>{t('notes:versions.item', { n: v.version })}</span>
                  <span className="muted small">
                    {formatDateTime(v.ts * 1000)} · {t('notes:charCount', { n: v.chars })}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {selected !== null && (
          <footer className="notes-dialog__foot">
            <span className="muted small">{t('notes:versions.revertHint', { n: selected })}</span>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={restore.isPending}
              onClick={() =>
                restore.mutate(
                  { id: noteId, version: selected },
                  {
                    onSuccess: () => {
                      addToast({
                        type: 'success',
                        message: t('notes:versions.revertDone', { n: selected }),
                      });
                      onClose();
                    },
                    onError: (e) =>
                      addToast({
                        type: 'error',
                        message: e instanceof Error ? e.message : t('notes:versions.revertFailed'),
                      }),
                  }
                )
              }
            >
              {t('notes:versions.revert')}
            </button>
          </footer>
        )}
      </aside>
    </ModalOverlay>
  );
}
