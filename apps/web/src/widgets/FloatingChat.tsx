/**
 * @file FloatingChat
 * @description Persistent floating chat window with two states: dot <-> panel.
 * Shares the chatStore and SSE channel with the chat page (both views use
 * hooks/useChatStream: history + online + subscribe).
 *
 * The dot shows an unread count when collapsed and new messages arrive; the
 * ask_user dialog is reused; navigation via agent.navigate keeps the
 * conversation running across pages. Hidden on the chat route by the shell
 * (AppShell renders this widget only off the chat route; the main chat
 * already lives there).
 *
 * Responsibilities:
 * - Toggle between the collapsed dot (with unread count) and the chat panel
 * - Reuse the chat stream hooks so the conversation persists across navigation
 * - Compose MessageList (with inline execution traces), AskDialog,
 *   ChatComposer and the LLM-missing tip
 * - Close on Escape only when no global modal sits above (modalDepth guard)
 */

import { useCallback, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { subscribe } from '@/bridge/stream';
import { useFloatingStore } from '@/stores/floatingStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSend } from '@/hooks/useChatSend';
import { interruptInstance } from '@/bridge/chatSend';
import { MessageList, TaskCards } from '@/widgets/chat/MessageList';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { ChatComposer } from '@/widgets/chat/ChatComposer';
import { NavIcons } from '@/components/icons/NavIcons';

export function FloatingChat() {
  const { t } = useTranslation('chat');
  const { open, unread, setOpen } = useFloatingStore();
  const navigate = useNavigate();
  const listRef = useRef<HTMLDivElement>(null);
  const firstSeqRef = useRef<number | null>(null);
  const messages = useChatStore((s) => s.messages);
  const connected = useChatStore((s) => s.connected);
  const thinking = useChatStore((s) => s.thinking);
  const composer = useChatSend();
  const { llmMissing } = composer;

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path); // The floating window survives navigation; the conversation continues
    },
    [navigate]
  );
  useChatStream(onNavigate);

  useEffect(() => {
    return subscribe(['agent.message'], () => {
      if (!useFloatingStore.getState().open) {
        useFloatingStore.setState((s) => ({ unread: s.unread + 1 }));
      }
    });
  }, []);

  const firstSeq = messages.length ? messages[0].seq : null;
  useEffect(() => {
    // A prepended older history page also grows messages.length; the loader
    // anchors the viewport itself, so only tail growth (or opening) snaps bottom
    const prev = firstSeqRef.current;
    firstSeqRef.current = firstSeq;
    if (prev !== null && firstSeq !== null && firstSeq < prev) return;
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [open, firstSeq, messages.length]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      // Yield to global modals (lightbox etc.): one Esc closes only the topmost modal
      if (useUIStore.getState().modalDepth > 0) return;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, setOpen]);

  if (!open) {
    return (
      <button
        type="button"
        className="float-dot"
        aria-label={unread > 0 ? t('chat:float.unread', { unread }) : t('chat:float.open')}
        aria-expanded={false}
        onClick={() => setOpen(true)}
      >
        <NavIcons.chat width={22} height={22} />
        {unread > 0 ? <span className="float-dot__unread">{Math.min(unread, 99)}</span> : null}
      </button>
    );
  }

  return (
    <div className="float-panel">
      <div className="float-panel__head">
        <span className="float-panel__title">{t('chat:float.title')}</span>
        <span className="small muted">
          {connected ? t('chat:float.online') : t('chat:float.reconnecting')}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => setOpen(false)}>
          {t('chat:float.collapse')}
        </button>
      </div>
      <div className="float-panel__body" ref={listRef}>
        <MessageList />
        <TaskCards />
      </div>
      {llmMissing ? <ChatLlmMissingTip /> : null}
      <ChatComposer
        composer={composer}
        className="float-panel__input"
        running={thinking}
        onStop={() => void interruptInstance('chat')}
        placeholder={
          llmMissing ? t('chat:composer.llmMissingPlaceholder') : t('chat:float.placeholder')
        }
      />
      <AskDialog />
    </div>
  );
}
