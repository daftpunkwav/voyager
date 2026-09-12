/**
 * @file noteQuote
 * @description Note-preview text selection: whitespace collapsing, truncation, and the explain message handed to the scout persona.
 *
 * Responsibilities:
 * - Normalize preview text selections (collapse whitespace, cap length)
 * - Keep the module-level last-selection cache the page probe reads
 * - Compose the localized explain message with the agent display name and
 *   note title
 */

import { i18n } from '@/i18n';

export const NOTES_QUOTE_MAX = 500;

/** A word/sentence dragged-selected in the preview: whitespace collapsed and truncated. An empty string means no valid selection. */
export function parseNotesQuote(raw: string | null | undefined): string {
  return String(raw ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, NOTES_QUOTE_MAX);
}

let lastExplainQuote = '';

export function rememberNotesQuote(quote: string): void {
  lastExplainQuote = parseNotesQuote(quote);
}

export function lastNotesExplainQuote(): string {
  return lastExplainQuote;
}

/** User-visible body of the explain request. agentName is the caller-supplied display name; this file is not bound to a specific persona. */
export function buildNoteExplainMessage(opts: {
  quote: string;
  agentName: string;
  title?: string;
}): string {
  const quote = parseNotesQuote(opts.quote);
  const who = (opts.agentName || '').trim() || i18n.t('notes:explain.assistant');
  const title = (opts.title || '').trim().slice(0, 80);
  const where = title
    ? i18n.t('notes:explain.whereTitled', { title })
    : i18n.t('notes:explain.whereUntitled');
  return i18n.t('notes:explain.message', { who, where, quote });
}
