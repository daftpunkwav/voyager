/**
 * @file PlanSection
 * @description The panel's plan section: the running agent's todo list for the
 * open session, each item marked with its status, plus the done/total counter
 * in the section head.
 *
 * Responsibilities:
 * - Render the plan items with their per-status mark
 * - Show the done/total counter as the section meta
 * - Show the empty hint when the plan is empty
 *
 * Constraints:
 * - Presentation only: the polled plan arrives through props, this section
 *   never polls or reads the store itself.
 */

import { useTranslation } from 'react-i18next';
import type { TodoItem } from '@/api/agent';
import { SideSection } from '@/widgets/chat/rightpanel/SideSection';

function TodoMark({ status }: { status: string }) {
  if (status === 'done') {
    return (
      <svg className="chat-side__mark chat-side__mark--done" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d="M8 12.5l2.7 2.7L16.5 9"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (status === 'in_progress') {
    return (
      <svg className="chat-side__mark chat-side__mark--doing" viewBox="0 0 24 24" aria-hidden>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
        <path
          d="M12 7.5A4.5 4.5 0 0 1 16.5 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg className="chat-side__mark" viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function PlanSection({
  todos,
  done,
  total,
}: {
  todos: TodoItem[];
  done: number;
  total: number;
}) {
  const { t } = useTranslation('chat');
  return (
    <SideSection title={t('chat:panel.plan')} meta={total > 0 ? `${done}/${total}` : undefined}>
      {todos.length > 0 ? (
        <ul className="chat-side__todos">
          {todos.map((it, i) => (
            <li key={i} className={`chat-side__todo chat-side__todo--${it.status}`}>
              <TodoMark status={it.status} />
              <span className="chat-side__content">{it.content}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="chat-side__empty small muted">{t('chat:panel.planEmpty')}</p>
      )}
    </SideSection>
  );
}
