/**
 * @file DeliveryCard
 * @description A dispatched teammate's structured delivery card: member head
 * + name, task title, status badge, elapsed time, and the full delivery as
 * collapsible Markdown (long answers fold to a preview; failures carry the
 * error and a jump into the run's execution view).
 *
 * Responsibilities:
 * - Render one agent.delivery row (done/failed variants)
 * - Collapse long content behind an expander; copy the full text
 * - Surface the run pointer for the agents-panel drill-in
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AgentCharacterHead } from '@/components/agent/avatars/AgentCharacterHead';
import { personaDisplayName } from '@/constants/personas';
import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';
import type { Delivery } from '@/stores/chatStore';

/** Characters at which the body folds (roughly a screenful of prose). */
const FOLD_CHARS = 900;

export function DeliveryCard({
  delivery,
  onOpenRun,
}: {
  delivery: Delivery;
  onOpenRun?: (runId: string) => void;
}) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const failed = delivery.status === 'failed';
  const name = personaDisplayName(delivery.member || delivery.name) || delivery.name;
  const body = failed ? (delivery.error ?? '') : delivery.content;
  const long = body.length > FOLD_CHARS;
  const shown = useMemo(
    () => (long && !open ? `${body.slice(0, FOLD_CHARS)}…` : body),
    [body, long, open]
  );

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(body);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable: the copy button simply stays inert */
    }
  };

  return (
    <div className={`delivery-card${failed ? ' delivery-card--failed' : ''}`} role="article">
      <div className="delivery-card__head">
        <span className="delivery-card__avatar" aria-hidden>
          <AgentCharacterHead
            agentId={delivery.member || 'orchestrator'}
            look={{ x: 0, y: 0 }}
            isFocused={false}
          />
        </span>
        <span className="delivery-card__name">{name}</span>
        <span className={`delivery-card__badge delivery-card__badge--${delivery.status}`}>
          {failed ? t('chat:delivery.failed') : t('chat:delivery.done')}
        </span>
        {delivery.title ? <span className="delivery-card__title">{delivery.title}</span> : null}
        {typeof delivery.elapsed_s === 'number' && delivery.elapsed_s > 0 ? (
          <span className="delivery-card__elapsed">
            {t('chat:delivery.elapsed', { s: delivery.elapsed_s })}
          </span>
        ) : null}
      </div>
      {failed ? (
        <div className="delivery-card__error">{body}</div>
      ) : (
        <div className="delivery-card__body chat-md">
          <ChatMarkdown content={shown} />
        </div>
      )}
      <div className="delivery-card__actions">
        {long ? (
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
            {open ? t('chat:delivery.collapse') : t('chat:delivery.expand')}
          </button>
        ) : null}
        <button type="button" onClick={() => void onCopy()}>
          {copied ? t('chat:msg.copied') : t('chat:msg.copy')}
        </button>
        {failed && delivery.run_id && onOpenRun ? (
          <button type="button" onClick={() => onOpenRun(delivery.run_id as string)}>
            {t('chat:delivery.openRun')}
          </button>
        ) : null}
      </div>
    </div>
  );
}
