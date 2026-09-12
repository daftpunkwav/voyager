/**
 * @file NoteBacklinks
 * @description Backlink panel: notes that reference the current note; clicking navigates to them.
 */

import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useBacklinks } from '@/hooks/useNotes';
import { routes } from '@/utils/routes';

export function BacklinkPanel({ noteId }: { noteId: string }) {
  const { t } = useTranslation('notes');
  const { data } = useBacklinks(noteId);
  const backlinks = data?.backlinks ?? [];
  if (backlinks.length === 0) return null;
  return (
    <div className="backlink-panel">
      <h4 className="small muted">{t('notes:backlinks.title', { n: backlinks.length })}</h4>
      <ul>
        {backlinks.map((b) => (
          <li key={b.id}>
            <Link to={routes.note(b.id)}>{b.title}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
