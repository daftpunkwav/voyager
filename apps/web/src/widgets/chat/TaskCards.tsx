/**
 * @file TaskCards
 * @description Live task.* progress cards for the chat side panel, with
 * completed/failed final states. Cards with a resource detail page are fully
 * clickable; graph job_ids have no detail page and stay display-only.
 *
 * Lives in its own module: the chat page passes it into RightPanel as
 * children, so the panel never has to import from the message timeline.
 */

import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chatStore';

export function TaskCards() {
  const { t } = useTranslation('chat');
  const cards = useChatStore((s) => s.cards);
  const order = useChatStore((s) => s.cardOrder);
  const visible = order.map((k) => cards[k]).filter((c): c is NonNullable<typeof c> => Boolean(c));
  if (visible.length === 0) return null;
  return (
    <div className="chat-cards">
      {visible.map((c) => {
        const cls = `chat-card chat-card--${c.status}`;
        const body = (
          <>
            <div className="chat-card__head">
              {/* Full id visible on hover while label is occupied by project/kind */}
              <span className="chat-card__label" title={c.key}>
                {c.label}
              </span>
              <span className="chat-card__stage small muted">
                {c.status === 'failed'
                  ? t('chat:task.failedStage', {
                      error: c.error ?? t('chat:task.errorNotProvided'),
                    })
                  : c.stage}
              </span>
            </div>
            <div className="chat-card__bar">
              <div
                className="chat-card__fill"
                style={{ width: `${Math.round(c.progress * 100)}%` }}
              />
            </div>
          </>
        );
        return c.link ? (
          <Link key={c.key} to={c.link} className={`${cls} chat-card--link`}>
            {body}
          </Link>
        ) : (
          <div key={c.key} className={cls}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
