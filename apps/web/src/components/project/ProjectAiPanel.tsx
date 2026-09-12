/**
 * @file ProjectAiPanel
 * @description One-shot AI analysis panel for a project: agent switcher, streaming message list, and run/abort controls.
 *
 * Responsibilities:
 * - Render the one-shot analysis stream and settled lines with per-line agents
 * - Provide the agent switcher and run / abort controls
 * - Auto-scroll to the newest line while output arrives
 */

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { AgentDefinition } from '@/constants/agentCatalog';
import type { AgentId } from '@/api/types';
import { StreamRenderer } from '@/components/agent/StreamRenderer';
import { AGENT_INITIALS } from '@/utils/labels';
import { GLASS_OUTER } from '@/constants/glassTokens';

export interface ProjectAiLine {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  agentId?: AgentId;
}

interface ProjectAiPanelProps {
  projectName: string;
  agents: AgentDefinition[];
  activeAgent: AgentId;
  lines: ProjectAiLine[];
  streaming: boolean;
  streamContent: string;
  streamThinking: string;
  onSelectAgent: (id: AgentId) => void;
  onRun: () => void;
  onAbort: () => void;
}

export function ProjectAiPanel({
  projectName,
  agents,
  activeAgent,
  lines,
  streaming,
  streamContent,
  streamThinking,
  onSelectAgent,
  onRun,
  onAbort,
}: ProjectAiPanelProps) {
  const { t } = useTranslation('sources');
  const bottomRef = useRef<HTMLDivElement>(null);
  const activeMeta = agents.find((a) => a.id === activeAgent) ?? agents[0];
  const initial = AGENT_INITIALS[activeAgent] ?? activeMeta?.name?.[0] ?? 'A';

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines, streaming, streamContent, streamThinking]);

  return (
    <div className={`pd-ai-panel embed-agent-chat ${GLASS_OUTER}`} data-testid="project-ai-panel">
      <header className="embed-agent-chat__head pd-ai-chat-head">
        <div className={`agent-avatar agent-${activeAgent} active`} aria-hidden>
          <span>{initial}</span>
        </div>
        <div className="pd-ai-chat-identity">
          <div className="embed-agent-chat__title">
            {activeMeta?.name ?? 'Agent'} · {activeMeta?.tagline ?? t('sources:ai.taglineFallback')}
          </div>
          <div className="embed-agent-chat__sub">
            {t('sources:ai.subtitle', { name: projectName })}
          </div>
        </div>
        <div className="pd-ai-agent-switch" role="tablist" aria-label={t('sources:ai.switchAria')}>
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              role="tab"
              className={`pd-ai-chip ${activeAgent === a.id ? 'is-active' : ''}`}
              aria-selected={activeAgent === a.id}
              disabled={streaming}
              title={a.intro}
              onClick={() => onSelectAgent(a.id as AgentId)}
            >
              {a.name}
            </button>
          ))}
        </div>
      </header>

      <div className="embed-agent-chat__messages pd-ai-chat-messages">
        {lines.map((l) => (
          <div key={l.id} className={`embed-msg embed-msg--${l.role}`}>
            {l.role === 'user' ? (
              l.content
            ) : (
              <StreamRenderer content={l.content} thinking={l.thinking} streaming={false} />
            )}
          </div>
        ))}
        {streaming && (
          <div className="embed-msg embed-msg--assistant embed-msg--streaming">
            {streamContent || streamThinking ? (
              <StreamRenderer
                content={streamContent}
                thinking={streamThinking || undefined}
                streaming
              />
            ) : (
              <span className="embed-msg--typing">
                {t('sources:ai.analyzing', { name: activeMeta?.name ?? 'Agent' })}
              </span>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="embed-agent-chat__input pd-ai-chat-actions">
        <p className="pd-ai-chat-hint">
          {streaming ? t('sources:ai.hintStreaming') : t('sources:ai.hintIdle')}
        </p>
        {streaming ? (
          <button
            type="button"
            className="btn btn-sm"
            onClick={onAbort}
            data-testid="project-ai-abort"
          >
            {t('sources:ai.abort')}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-sm pd-ai-run-btn"
            onClick={onRun}
            data-testid="project-ai-run"
          >
            {lines.some((l) => l.role === 'assistant')
              ? t('sources:ai.rerun')
              : t('sources:ai.run')}
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              width={14}
              height={14}
              aria-hidden
            >
              <path d="M5 12h14M13 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </div>

      <footer className="embed-agent-chat__footer">
        <span className="mono">{activeMeta?.name ?? 'Agent'}</span>
        <span className="embed-agent-chat__hint">{t('sources:ai.footerHint')}</span>
      </footer>
    </div>
  );
}
