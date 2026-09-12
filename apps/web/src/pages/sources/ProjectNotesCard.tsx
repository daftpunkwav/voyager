/**
 * @file ProjectNotesCard
 * @description Project notes panel of the project detail page (content of the notes list tab).
 *
 * Responsibilities:
 * - List the project's notes with dates and links into the notes
 *   workspace
 * - Raise the new-note action (the coordinator navigates to
 *   /notes?project=) and show the empty state
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import type { Note } from '@/api/types';
import { EmptyState } from '@/components/common/EmptyState';
import { formatDate } from '@/utils/date';
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';

interface ProjectNotesCardProps {
  notes: Note[];
  /** Detail project id (link-back query param; an empty string is appended when missing) */
  projectId: string | undefined;
  /** Creates a new note (coordinator page navigates to /notes?project=) */
  onNewNote: () => void;
}

/** Notes tab content: toolbar plus note list (empty state via EmptyState) */
export function ProjectNotesCard({ notes, projectId, onNewNote }: ProjectNotesCardProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={`pd-notes-panel ${GLASS_OUTER}`}>
      <div className="pd-notes-toolbar">
        <div>
          <h3 className="pd-notes-title">{t('sources:notesCard.title')}</h3>
          <p className="muted small">{t('sources:notesCard.meta', { count: notes.length })}</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={onNewNote}>
          {t('sources:notesCard.new')}
        </button>
      </div>

      {notes.length === 0 ? (
        <EmptyState
          title={t('sources:notesCard.emptyTitle')}
          description={t('sources:notesCard.emptyDesc')}
        />
      ) : (
        <ul className="pd-notes-list">
          {notes.map((n) => (
            <li key={n.id}>
              <Link
                to={`/notes?note=${n.id}&project=${projectId ?? ''}`}
                className={`pd-notes-list-item ${GLASS_INNER}`}
              >
                <span className="pd-notes-list-item__title">{n.title}</span>
                <span className="pd-notes-list-item__meta">{formatDate(n.updated_at)}</span>
                <span className="pd-notes-list-item__snippet">
                  {(n.content ?? '').replace(/[#*`]/g, '').slice(0, 100)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
