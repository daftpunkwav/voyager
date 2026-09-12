/**
 * @file ChatComposer
 * @description Shared chat composer: textarea plus send/stop button, used by the
 * chat page and the persistent floating window. Each surface owns its own
 * useChatSend instance (drafts stay per surface by design) and passes it in.
 *
 * Responsibilities:
 * - Bind the draft and disable on sending / llmMissing / empty draft
 * - Enter sends, Shift+Enter inserts a newline, IME composition never sends
 * - While the agent is running (thinking) the button morphs into the stop
 *   button that interrupts the current turn — one control, mode-dependent
 * - Render the surface-provided placeholder (the llmMissing copy is chosen
 *   by the caller, which already holds the flag for its degrade tip)
 */

import { useTranslation } from 'react-i18next';
import type { UseChatSendReturn } from '@/hooks/useChatSend';

interface ChatComposerProps {
  /** Send state from the surface-owned useChatSend instance */
  composer: UseChatSendReturn;
  /** Placeholder copy; callers with an llmMissing degrade tip pass the swapped copy here */
  placeholder: string;
  /** Wrapper class: the page and the floating panel lay the composer out differently */
  className: string;
  /** The agent is running: the send button becomes the stop button */
  running?: boolean;
  /** Interrupt the current turn (required when running is passed) */
  onStop?: () => void;
}

export function ChatComposer({
  composer,
  placeholder,
  className,
  running = false,
  onStop,
}: ChatComposerProps) {
  const { t } = useTranslation('chat');
  const { draft, setDraft, sending, llmMissing, send } = composer;
  const stopping = running && Boolean(onStop);
  return (
    <div className={className}>
      <textarea
        rows={2}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          // isComposing: Enter that confirms an IME candidate must not send
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send();
          }
        }}
      />
      {stopping ? (
        <button type="button" className="btn btn-danger chat-stop" onClick={onStop}>
          {t('chat:composer.stop')}
        </button>
      ) : (
        <button
          type="button"
          className="btn btn-primary"
          disabled={sending || llmMissing || !draft.trim()}
          onClick={() => void send()}
        >
          {t('chat:composer.send')}
        </button>
      )}
    </div>
  );
}
