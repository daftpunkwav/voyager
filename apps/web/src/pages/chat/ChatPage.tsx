/**
 * @file ChatPage
 * @description Main chat page: two-column layout with the conversation on the
 * left and a progress sidebar (plan + running subagents) on the right.
 *
 * History is rebuilt via GET /api/chat/messages, sends go through useChatSend,
 * and streaming updates arrive over SSE via hooks/useChatStream. Shares the
 * same chatStore with the persistent overlay window; the gateway keeps no session table.
 *
 * Responsibilities:
 * - Wire the SSE stream with navigation raised to react-router
 * - Tab between the conversation (message list with inline execution traces,
 *   ask dialog, composer) and the full trajectory view (per-turn execution
 *   detail rebuilt from persisted rows), with a session-log shortcut
 * - Host the right panel: plan (todos), running subagents and deliverables
 */

import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chatStore';
import { useChatStream } from '@/hooks/useChatStream';
import { useChatSend } from '@/hooks/useChatSend';
import { interruptInstance } from '@/bridge/chatSend';
import { MessageList } from '@/widgets/chat/MessageList';
import { TrajectoryView } from '@/widgets/chat/TrajectoryView';
import { RightPanel } from '@/widgets/chat/RightPanel';
import { TaskCards } from '@/widgets/chat/MessageList';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { AskDialog } from '@/widgets/chat/AskDialog';
import { ChatComposer } from '@/widgets/chat/ChatComposer';
import { SessionDrawer } from '@/widgets/chat/SessionDrawer';

export function ChatPage() {
  const { t } = useTranslation('chat');
  const navigate = useNavigate();
  const thinking = useChatStore((s) => s.thinking);
  const connected = useChatStore((s) => s.connected);
  const composer = useChatSend();
  const { llmMissing } = composer;
  const [view, setView] = useState<'chat' | 'trajectory'>('chat');
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const onNavigate = useCallback(
    (path: string) => {
      navigate(path);
    },
    [navigate]
  );
  useChatStream(onNavigate);

  return (
    <section className="chat-page chat-layout">
      <div className="chat-main">
        <div className="chat-tabs">
          <div className="chat-tabs__group" role="tablist" aria-label={t('chat:traj.tabsLabel')}>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'chat'}
              className={`chat-tabs__tab${view === 'chat' ? ' chat-tabs__tab--active' : ''}`}
              onClick={() => setView('chat')}
            >
              {t('chat:traj.tabChat')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'trajectory'}
              className={`chat-tabs__tab${view === 'trajectory' ? ' chat-tabs__tab--active' : ''}`}
              onClick={() => setView('trajectory')}
            >
              {t('chat:traj.tabTrajectory')}
            </button>
          </div>
          <span className="small muted" role="status">
            {connected ? t('chat:float.online') : t('chat:float.reconnecting')}
          </span>
          <button type="button" className="btn btn-sm" onClick={() => setSessionsOpen(true)}>
            {t('chat:session.drawerButton')}
          </button>
          <button type="button" className="btn btn-sm" onClick={() => navigate('/activity')}>
            {t('chat:traj.sessionLog')}
          </button>
        </div>
        {view === 'chat' ? (
          <>
            <MessageList />
            {llmMissing ? <ChatLlmMissingTip /> : null}
            <ChatComposer
              composer={composer}
              className="chat-input"
              running={thinking}
              onStop={() => void interruptInstance('chat')}
              placeholder={
                llmMissing
                  ? t('chat:composer.llmMissingPlaceholder')
                  : t('chat:composer.placeholder')
              }
            />
            <AskDialog />
          </>
        ) : (
          <TrajectoryView />
        )}
      </div>
      <RightPanel taskCards={<TaskCards />} />
      <SessionDrawer open={sessionsOpen} onClose={() => setSessionsOpen(false)} />
    </section>
  );
}
