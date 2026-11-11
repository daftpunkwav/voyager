/**
 * @file DeliveryCardActions
 * @description The action row of a delivery card: the expander of a long
 * answer, the copy button, and the run pointer of a failed delivery. The
 * handlers behind them live in useDeliveryCardActions.
 *
 * Responsibilities:
 * - Own the fold state and the clipboard feedback of the card
 * - Render the expander, the copy button, and the run drill-in button
 *
 * Constraints:
 * - The expander only appears for a body that can be unfolded
 * - The run drill-in only appears for a failed delivery that has a run
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Delivery } from '@/stores/chatStore';
import { deliveryText, isFoldable } from './deliveryContent';

/** The interactive state of a delivery card and the handlers behind it. */
export interface DeliveryCardActionState {
  /** Whether the folded answer is expanded. */
  open: boolean;
  /** Whether the last copy succeeded (the button shows "copied" briefly). */
  copied: boolean;
  /** Whether the body is long enough to fold behind the expander. */
  foldable: boolean;
  /** Toggle the fold of the answer. */
  toggleOpen: () => void;
  /** Copy the delivery text to the clipboard. */
  copy: () => Promise<void>;
}

/** The fold state and the clipboard handler of a delivery card. */
export function useDeliveryCardActions(delivery: Delivery): DeliveryCardActionState {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = deliveryText(delivery);
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard unavailable: the copy button simply stays inert */
    }
  };
  return {
    open,
    copied,
    foldable: isFoldable(text),
    toggleOpen: () => setOpen((v) => !v),
    copy,
  };
}

export function DeliveryCardActions({
  delivery,
  actions,
  onOpenRun,
}: {
  delivery: Delivery;
  actions: DeliveryCardActionState;
  onOpenRun?: (runId: string) => void;
}) {
  const { t } = useTranslation('chat');
  const { open, copied, foldable, toggleOpen, copy } = actions;
  const failed = delivery.status === 'failed';
  return (
    <div className="delivery-card__actions">
      {foldable ? (
        <button type="button" aria-expanded={open} onClick={toggleOpen}>
          {open ? t('chat:delivery.collapse') : t('chat:delivery.expand')}
        </button>
      ) : null}
      <button type="button" onClick={() => void copy()}>
        {copied ? t('chat:msg.copied') : t('chat:msg.copy')}
      </button>
      {failed && delivery.run_id && onOpenRun ? (
        <button
          type="button"
          onClick={() => {
            if (delivery.run_id) onOpenRun(delivery.run_id);
          }}
        >
          {t('chat:delivery.openRun')}
        </button>
      ) : null}
    </div>
  );
}
