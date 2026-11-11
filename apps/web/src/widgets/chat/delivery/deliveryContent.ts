/**
 * @file deliveryContent
 * @description The content rules of a delivery card: which text the card
 * carries (the teammate's answer, or the failure message) and when that
 * text folds behind the expander.
 *
 * Responsibilities:
 * - Pick the text a delivery card shows
 * - Apply the fold threshold shared by the body and the expander
 *
 * Constraints:
 * - A failed delivery carries its error message, never the answer
 * - The fold threshold must stay identical for the body and the expander,
 *   so the expander only appears when there is something to unfold
 */

import type { Delivery } from '@/stores/chatStore';

/** Characters at which the body folds (roughly a screenful of prose). */
const FOLD_CHARS = 900;

/** The text of a delivery card: the failure message, else the answer. */
export function deliveryText(delivery: Delivery): string {
  return delivery.status === 'failed' ? (delivery.error ?? '') : delivery.content;
}

/** Whether the text is long enough to fold behind the expander. */
export function isFoldable(text: string): boolean {
  return text.length > FOLD_CHARS;
}

/** The text as shown: a preview while folded, the full text when expanded. */
export function foldText(text: string, open: boolean): string {
  return isFoldable(text) && !open ? `${text.slice(0, FOLD_CHARS)}…` : text;
}
