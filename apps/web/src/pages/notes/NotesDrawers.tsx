/**
 * @file NotesDrawers
 * @description Aggregates the notes-page drawers: versions panel, trash panel, and delete confirmation dialog.
 *
 * Responsibilities:
 * - Mount the versions / trash / delete drawers for the workspace
 * - Run note deletion and route back to the notes index afterwards
 * - Close drawers through the notes view pipeline (commitNotesPanel) so
 *   the state stays persisted and agent-synced
 */

import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useDeleteNote } from '@/hooks/useNotes';
import { useUIStore } from '@/stores/uiStore';
import { routes } from '@/utils/routes';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { TrashPanel } from './NoteTrash';
import { VersionPanel } from './NoteVersions';
import { commitNotesPanel } from './notesView';

interface NotesDrawersProps {
  /** The note being edited is persisted (drafts have no version/delete semantics). */
  persisted: boolean;
  editingNoteId: string;
  versionsOpen: boolean;
  onCloseVersions: () => void;
  trashOpen: boolean;
  deleteOpen: boolean;
  onCloseDelete: () => void;
}

export function NotesDrawers({
  persisted,
  editingNoteId,
  versionsOpen,
  onCloseVersions,
  trashOpen,
  deleteOpen,
  onCloseDelete,
}: NotesDrawersProps) {
  const { t } = useTranslation('notes');
  const navigate = useNavigate();
  const deleteNote = useDeleteNote();
  const addToast = useUIStore((s) => s.addToast);

  return (
    <>
      <VersionPanel
        noteId={persisted ? editingNoteId : ''}
        open={versionsOpen && persisted}
        onClose={onCloseVersions}
      />
      <TrashPanel open={trashOpen} onClose={() => commitNotesPanel('none')} />
      <ConfirmDialog
        open={deleteOpen}
        title={t('notes:delete.title')}
        message={t('notes:delete.confirm')}
        confirmLabel={t('notes:trash.move')}
        danger
        onConfirm={() => {
          if (persisted) {
            void deleteNote.mutateAsync(editingNoteId).then(
              () => {
                addToast({ type: 'success', message: t('notes:delete.done') });
                navigate(routes.notes);
              },
              (err: unknown) =>
                addToast({
                  type: 'error',
                  message: err instanceof Error ? err.message : t('notes:delete.failed'),
                })
            );
          }
          onCloseDelete();
        }}
        onCancel={onCloseDelete}
      />
    </>
  );
}
