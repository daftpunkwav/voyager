/**
 * @file DeliveryCardBody
 * @description The body of a delivery card: the teammate's answer as
 * Markdown, or the failure message of a failed delivery. A long answer
 * folds to a preview behind the card's expander.
 *
 * Responsibilities:
 * - Render the error text of a failed delivery
 * - Render the answer as Markdown, folded to a preview while it is long
 *
 * Constraints:
 * - A failed delivery shows its error message in full; the fold applies to
 *   the answer only
 */

import { useMemo } from 'react';
import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';
import type { Delivery } from '@/stores/chatStore';
import { deliveryText, foldText } from './deliveryContent';

export function DeliveryCardBody({ delivery, open }: { delivery: Delivery; open: boolean }) {
  const text = deliveryText(delivery);
  // Memoized: the answer can be long, and re-slicing it on every render of
  // the card is wasted work.
  const shown = useMemo(() => foldText(text, open), [text, open]);
  if (delivery.status === 'failed') {
    return <div className="delivery-card__error">{text}</div>;
  }
  return (
    <div className="delivery-card__body chat-md">
      <ChatMarkdown content={shown} />
    </div>
  );
}
