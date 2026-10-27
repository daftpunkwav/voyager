/**
 * @file DeliveryCard
 * @description A dispatched teammate's structured delivery card: member head
 * + name, task title, status badge, elapsed time, and the full delivery as
 * collapsible Markdown (long answers fold to a preview; failures carry the
 * error and a jump into the run's execution view).
 *
 * Responsibilities:
 * - Render the head of one agent.delivery row (done/failed variants)
 * - Hand the body and the actions to their own modules
 *
 * The body and the action handlers live in the delivery/ submodules, so this
 * card stays the head plus composition.
 */

import { useTranslation } from 'react-i18next';
import { AgentCharacterHead } from '@/components/agent/avatars/AgentCharacterHead';
import { personaDisplayName } from '@/constants/personas';
import type { Delivery } from '@/stores/chatStore';
import { DeliveryCardActions, useDeliveryCardActions } from './delivery/DeliveryCardActions';
import { DeliveryCardBody } from './delivery/DeliveryCardBody';

export function DeliveryCard({
  delivery,
  onOpenRun,
}: {
  delivery: Delivery;
  onOpenRun?: (runId: string) => void;
}) {
  const { t } = useTranslation('chat');
  const failed = delivery.status === 'failed';
  const name = personaDisplayName(delivery.member || delivery.name) || delivery.name;
  const actions = useDeliveryCardActions(delivery);

  return (
    <article className={`delivery-card${failed ? ' delivery-card--failed' : ''}`}>
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
      <DeliveryCardBody delivery={delivery} open={actions.open} />
      <DeliveryCardActions delivery={delivery} actions={actions} onOpenRun={onOpenRun} />
    </article>
  );
}
