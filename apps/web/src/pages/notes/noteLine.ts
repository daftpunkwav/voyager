/**
 * @file noteLine
 * @description Line-level operations on note content: draft ids, line-prefix toggling, and split-pane scroll ratio sync.
 *
 * Responsibilities:
 * - Distinguish draft ids ('new') from persisted note ids
 * - Toggle line prefixes, preserving task-list markers
 * - Sync scroll position between panes by ratio
 */

/** A draft id is exactly 'new'; everything else counts as a persisted note. */
export function isPersistedNoteId(id: string | null | undefined): id is string {
  return Boolean(id && id !== 'new');
}

/**
 * Line-prefix toggle: removes the prefix if already present, otherwise strips
 * any old heading/quote/list prefix before applying the new one. `- ` does not
 * swallow task-list items (`- [ ] `).
 */
export function applyLinePrefix(text: string, prefix: string): string {
  const isTask = /^[-*]\s\[[ x]\]\s/.test(text);
  if (text.startsWith(prefix) && !(prefix === '- ' && isTask)) {
    return text.slice(prefix.length);
  }
  const stripped = text.replace(/^(#{1,6}\s|>\s?|[-*]\s(?:\[[ x]\]\s)?|\d+\.\s)/, '');
  return prefix + stripped;
}

/** Syncs `from` to `to` by scroll ratio; skips when either side has no scrollable distance. */
export function syncScrollRatio(from: HTMLElement, to: HTMLElement): void {
  const fromMax = from.scrollHeight - from.clientHeight;
  const toMax = to.scrollHeight - to.clientHeight;
  if (fromMax <= 0 || toMax <= 0) return;
  to.scrollTop = (from.scrollTop / fromMax) * toMax;
}
