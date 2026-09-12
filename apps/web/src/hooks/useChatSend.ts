/**
 * @file useChatSend
 * @description Send hook shared by the chat page and the floating window.
 *
 * Owns draft/sending/llmMissing/send. Sends pass a daily token-quota guard
 * (full quota blocks the send and keeps the draft); on failure the draft is
 * restored, a system bubble is appended and thinking is cleared. The input
 * DOM is the shared ChatComposer widget; the draft state itself stays per
 * surface (one hook instance each).
 *
 * Responsibilities:
 * - Own draft/sending/llmMissing state for both chat surfaces
 * - Run the quota guard before sends: block with an error toast at full
 *   quota, warn once per mount past the threshold, then send
 * - On failure restore the draft, append a system bubble, and clear the
 *   thinking indicator
 */

import { useRef, useState } from 'react';
import { postChatMessage } from '@/bridge/chatSend';
import { fetchQuotaGuard, quotaWarnMessage } from '@/bridge/quotaGuard';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useLlmAvailable } from './useLlmAvailable';
import { i18n } from '@/i18n';

/** Send state consumed by the shared ChatComposer widget. */
export interface UseChatSendReturn {
  draft: string;
  setDraft: (v: string) => void;
  sending: boolean;
  llmMissing: boolean;
  send: () => Promise<void>;
}

export function useChatSend(): UseChatSendReturn {
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const llm = useLlmAvailable();
  const llmMissing = llm === 'missing';
  // Warn about >=80% quota only once per mounted session to avoid toast spam
  // during rapid sends; remounting (page change / reopened floating window) resets it
  const quotaWarnedRef = useRef(false);

  const send = async () => {
    const content = draft.trim();
    if (!content || sending || llmMissing) return;
    // While the agent is running the composer button is the stop button: sending
    // mid-turn is intentionally unavailable (interrupt first, then speak)
    if (useChatStore.getState().thinking) return;
    // Set sending before the guard: it is an async query, and without setting
    // first the send could be re-entered twice within the query window
    setSending(true);
    try {
      // Quota guard before sending: full quota blocks and keeps the draft; >=80% warns and still sends
      const guard = await fetchQuotaGuard();
      if (guard.action === 'block') {
        useUIStore.getState().addToast({ type: 'error', message: guard.reason });
        return;
      }
      if (guard.action === 'warn' && !quotaWarnedRef.current) {
        quotaWarnedRef.current = true;
        useUIStore.getState().addToast({ type: 'warning', message: quotaWarnMessage(guard.ratio) });
      }
      setDraft('');
      const seq = await postChatMessage(
        content,
        useChatStore.getState().activeSessionId || undefined
      );
      useChatStore.getState().appendLocal({ seq, role: 'user', content });
    } catch (err) {
      setDraft(content);
      // addSystem must not set thinking: a system bubble is not "agent thinking",
      // and setting it would leave the indicator hanging until SSE clears it
      useChatStore
        .getState()
        .addSystem(err instanceof Error ? err.message : i18n.t('chat:send.failedUnreachable'));
      useChatStore.getState().clearThinking();
    } finally {
      setSending(false);
    }
  };

  return { draft, setDraft, sending, llmMissing, send };
}
