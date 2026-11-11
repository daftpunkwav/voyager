/**
 * @file DeliverablesSection
 * @description The panel's deliverables section: the note artifacts the
 * session produced (each linking to its note) plus the live task progress
 * cards the chat page passes in.
 *
 * Responsibilities:
 * - Render the note artifacts as links to their note
 * - Render the task progress cards passed in by the chat page
 * - Show the empty hint when the session produced nothing
 *
 * Constraints:
 * - Presentation only: the artifacts arrive through props and the task cards
 *   as a slot; this section never reads the store itself.
 */

import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { type NoteArtifact } from '@/stores/chatStore';
import { routes } from '@/utils/routes';
import { SideSection } from '@/widgets/chat/rightpanel/SideSection';

export function DeliverablesSection({
  artifacts,
  cardCount,
  taskCards,
}: {
  artifacts: NoteArtifact[];
  cardCount: number;
  taskCards: ReactNode;
}) {
  const { t } = useTranslation('chat');
  const hasDeliverables = artifacts.length > 0 || cardCount > 0;
  return (
    <SideSection
      title={t('chat:panel.deliverables')}
      meta={hasDeliverables ? artifacts.length + cardCount : undefined}
    >
      {artifacts.length > 0 ? (
        <ul className="chat-side__artifacts">
          {artifacts.map((a) => (
            <li key={a.seq}>
              <Link to={routes.note(a.noteId)} className="chat-side__artifact" title={a.title}>
                <svg className="chat-side__artifact-icon" viewBox="0 0 24 24" aria-hidden>
                  <path
                    d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5L13.5 3z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M13.5 3v5.5H19"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.9"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="chat-side__artifact-title">{a.title}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
      {taskCards}
      {!hasDeliverables ? (
        <p className="chat-side__empty small muted">{t('chat:panel.deliverablesEmpty')}</p>
      ) : null}
    </SideSection>
  );
}
