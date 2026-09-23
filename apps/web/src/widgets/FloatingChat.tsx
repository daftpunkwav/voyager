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

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';
import { useFloatingStore } from '@/stores/floatingStore';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSend } from '@/hooks/useChatSend';
import { interruptInstance } from '@/bridge/chatSend';
import { MessageList } from '@/widgets/chat/MessageList';
import { TaskCards } from '@/widgets/chat/TaskCards';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { ChatComposer } from '@/widgets/chat/ChatComposer';
import { NavIcons } from '@/components/icons/NavIcons';

/** How long the panel exit animation plays before the dot takes over. Keep in
 *  sync with the --float-out duration in shell.css. */
const FLOAT_EXIT_MS = 160;

export function FloatingChat() {
  const { t } = useTranslation('chat');
  const { open, unread, setOpen } = useFloatingStore();
  const navigate = useNavigate();
  const listRef = useRef<HTMLDivElement>(null);
  const firstSeqRef = useRef<number | null>(null);
  // `seenOpen` + `leaving` keep the panel mounted through its exit animation
  // before the collapsed dot takes over, mirroring ModalOverlay's lifecycle.
  const seenOpen = useRef(open);
  const [leaving, setLeaving] = useState(false);
  const messages = useChatStore((s) => s.messages);
  const connected = useChatStore((s) => s.connected);
  const thinking = useChatStore((s) => s.thinking);
  const composer = useChatSend();
  const { llmMissing } = composer;

  if (open) seenOpen.current = true;

  useEffect(() => {
    if (!open && seenOpen.current) {
      seenOpen.current = false;
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), FLOAT_EXIT_MS);
      return () => window.clearTimeout(timer);
    }
  }, [open]);

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path); // The floating window survives navigation; the conversation continues
    },
    [navigate]
  );
  useChatStream(onNavigate);

  useEffect(() => {
    return subscribe([EventType.AGENT_MESSAGE], () => {
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

  if (!open && !leaving) {
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
    <div className={`float-panel${!open && leaving ? ' is-leaving' : ''}`}>
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
        onManageModels={() => navigate('/settings')}
        placeholder={
          llmMissing ? t('chat:composer.llmMissingPlaceholder') : t('chat:float.placeholder')
        }
      />
      <AskDialog />
    </div>
  );
}
