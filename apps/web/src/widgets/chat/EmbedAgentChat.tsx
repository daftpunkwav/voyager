/**
 * @file EmbedAgentChat
 * @description Compact embedded chat panel for the import assistant and graph guide modes.
 *
 * User turns go through the main chat bridge; local lines are appended only
 * after the send resolves, and the LLM-missing state renders its own inline
 * tip instead of delegating to the host.
 *
 * Responsibilities:
 * - Compose mode-specific prompts (import context or the selected graph node)
 * - Send user turns via sendUserTurn and append local lines only after it resolves
 * - Keep the draft on failure, toast errors, and render its own LLM-missing tip
 */
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import type { ImportAssistContext } from '@/api/types';
import { sendUserTurn } from '@/bridge/chatSend';
import { useLlmAvailable } from '@/hooks/useLlmAvailable';
import { ChatLlmMissingTip } from '@/widgets/chat/ChatLlmMissingTip';
import { useUIStore } from '@/stores/uiStore';

export type EmbedChatMode = 'import' | 'graph';

interface ChatLine {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface EmbedAgentChatProps {
  mode: EmbedChatMode;
  title: string;
  subtitle?: string;
  agentInitial?: string;
  agentClassName?: string;
  importContext?: ImportAssistContext;
  graphNodeId?: string | null;
  placeholder?: string;
}

export function EmbedAgentChat({
  mode,
  title,
  subtitle,
  agentInitial = 'A',
  agentClassName = 'agent-orchestrator',
  importContext,
  graphNodeId,
  placeholder,
}: EmbedAgentChatProps) {
  const { t } = useTranslation('agent');
  const [lines, setLines] = useState<ChatLine[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: mode === 'import' ? t('agent:embed.welcomeImport') : t('agent:embed.welcomeGraph'),
    },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const addToast = useUIStore((s) => s.addToast);
  const llm = useLlmAvailable();
  const llmMissing = llm === 'missing';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  const buildPrompt = (text: string): string => {
    if (mode === 'graph') {
      const node = graphNodeId || t('agent:embed.graphUnselected');
      return t('agent:embed.graphPrompt', { node, text });
    }
    const ctx = importContext ?? { mode: 'stars' as const };
    const sep = t('agent:embed.listSeparator');
    const available = (ctx.available_repo_keys ?? []).join(sep) || t('agent:embed.importNone');
    const selected = (ctx.selected_repo_keys ?? []).join(sep) || t('agent:embed.importNone');
    return t('agent:embed.importPrompt', { available, selected, text });
  };

  const send = async () => {
    const text = input.trim();
    if (!text || sending || llmMissing) return;
    setSending(true);
    const prompt = buildPrompt(text);
    try {
      // Local view state is only updated after sendUserTurn resolves: if the
      // quota block throws, the input is preserved and no false
      // "sent to main conversation" system line is inserted.
      await sendUserTurn(prompt);
      setInput('');
      setLines((prev) => [
        ...prev,
        { id: `u_${Date.now()}`, role: 'user', content: text },
        { id: `sys_${Date.now()}`, role: 'system', content: t('agent:embed.sentToMain') },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : t('agent:embed.sendFailed');
      addToast({ type: 'error', message });
    } finally {
      setSending(false);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  if (llmMissing) {
    return (
      <div className="embed-agent-chat">
        <header className="embed-agent-chat__head">
          <div className={`agent-avatar ${agentClassName} active`}>
            <span>{agentInitial}</span>
          </div>
          <div>
            <div className="embed-agent-chat__title">{title}</div>
            {subtitle && <div className="embed-agent-chat__sub">{subtitle}</div>}
          </div>
        </header>
        <div style={{ padding: 12 }}>
          <ChatLlmMissingTip />
        </div>
      </div>
    );
  }

  return (
    <div className="embed-agent-chat">
      <header className="embed-agent-chat__head">
        <div className={`agent-avatar ${agentClassName} active`}>
          <span>{agentInitial}</span>
        </div>
        <div>
          <div className="embed-agent-chat__title">{title}</div>
          {subtitle && <div className="embed-agent-chat__sub">{subtitle}</div>}
        </div>
      </header>
      <div className="embed-agent-chat__messages">
        {lines.map((l) => (
          <div key={l.id} className={`embed-msg embed-msg--${l.role}`}>
            {l.content}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="embed-agent-chat__input">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? t('agent:embed.defaultPlaceholder')}
          disabled={sending}
          aria-label={t('agent:embed.inputAria', { title })}
        />
        <button
          type="button"
          className="embed-send-btn"
          onClick={() => void send()}
          disabled={sending || !input.trim()}
          aria-label={t('agent:embed.send')}
          title={t('agent:embed.sendTitle')}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            width={16}
            height={16}
          >
            <path d="M5 12h14M13 5l7 7-7 7" />
          </svg>
        </button>
      </div>
      <footer className="embed-agent-chat__footer">
        <span className="embed-agent-chat__hint">
          {mode === 'import' ? t('agent:embed.hintImport') : t('agent:embed.hintGraph')}
        </span>
      </footer>
    </div>
  );
}
