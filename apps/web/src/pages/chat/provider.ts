/**
 * @file provider
 * @description Page-awareness probe for the chat page.
 *
 * Reports only the message count; zero is reported as well because an empty
 * conversation is real state.
 *
 * Responsibilities:
 * - Read the timeline length straight from chatStore (no module cache
 *   needed: the store is shared state)
 * - Report a localized index line plus the message count
 */

import type { PageProbe } from '@/bridge/pageContext';
import { i18n } from '@/i18n';
import { useChatStore } from '@/stores/chatStore';

export const chatProvider: PageProbe = {
  page: 'chat',
  report() {
    const n = useChatStore.getState().messages.length;
    return { summary: i18n.t('chat:provider.summary', { n }), counts: { messages: n } };
  },
};
