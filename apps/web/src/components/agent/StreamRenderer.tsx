/**
 * @file StreamRenderer
 * @description Streaming Markdown body with a collapsible thinking panel.
 *
 * Real thinking content is collapsed by default (and forced collapsed once
 * body text exists); scaffold-only thinking never opens the panel. Body
 * updates are throttled while streaming.
 *
 * Responsibilities:
 * - Partition thinking from body text and coalesce empty-body streams
 * - Throttle body re-rendering while streaming and collapse long bodies on demand
 * - Toggle the thinking panel: collapsed by default, forced closed once body text exists
 * - Pick streaming placeholder copy from thinking keywords
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import {
  coalesceEmptyBodyWithThinking,
  isDispatchNoticeOnly,
  isStatusLine,
  isStatusOnlyThinking,
  partitionThinking,
  persistableThinking,
} from '@/utils/agentThinking';

export {
  coalesceEmptyBodyWithThinking,
  isDispatchNoticeOnly,
  isStatusLine,
  isStatusOnlyThinking,
  partitionThinking,
  persistableThinking,
};

interface StreamRendererProps {
  content: string;
  thinking?: string;
  streaming: boolean;
  /** Whether the thinking panel starts expanded; collapsed by default. */
  thinkingOpen?: boolean;
  /** Collapse only the body without touching the thinking panel (for long content). */
  collapseBody?: boolean;
}

/** Streaming Markdown; real thinking is collapsed by default and scaffold thinking never enters the panel. */
export function StreamRenderer({
  content,
  thinking,
  streaming,
  thinkingOpen = false,
  collapseBody = false,
}: StreamRendererProps) {
  const { t } = useTranslation('agent');
  const coalesced = coalesceEmptyBodyWithThinking(content, thinking);
  const displayContent = coalesced.content;
  const displayThinking = coalesced.thinking;

  const [rendered, setRendered] = useState(displayContent);
  const [thinkingExpanded, setThinkingExpanded] = useState(thinkingOpen);

  useEffect(() => {
    if (!streaming) {
      setRendered(displayContent);
      return;
    }
    const t = setTimeout(() => setRendered(displayContent), 32);
    return () => clearTimeout(t);
  }, [displayContent, streaming]);

  const thinkingTrim = displayThinking.trim();
  const { realThinking } = partitionThinking(thinkingTrim);
  const hasRealThinking = Boolean(realThinking);
  const hasBody = Boolean(rendered && rendered.trim());
  const thinkingLines = hasRealThinking ? realThinking.split('\n').filter(Boolean).length : 0;

  // Force collapse once body text exists; never auto-expand during streaming.
  useEffect(() => {
    if (hasBody && hasRealThinking) {
      setThinkingExpanded(false);
    }
  }, [hasBody, hasRealThinking]);

  // Sync once when the caller explicitly requests expansion.
  useEffect(() => {
    if (thinkingOpen) setThinkingExpanded(true);
  }, [thinkingOpen]);

  const showThinkingPanel = hasRealThinking;

  return (
    <div className="stream-renderer" data-testid="stream-renderer">
      {showThinkingPanel && (
        <div
          className="stream-renderer__thinking"
          data-open={thinkingExpanded ? '1' : '0'}
          data-testid="thinking-panel"
        >
          <button
            type="button"
            className="stream-renderer__thinking-toggle"
            aria-expanded={thinkingExpanded}
            onClick={() => setThinkingExpanded((v) => !v)}
          >
            <span className="stream-renderer__thinking-caret" aria-hidden>
              {thinkingExpanded ? '▾' : '▸'}
            </span>
            <span className="stream-renderer__thinking-title">{t('agent:thinking.title')}</span>
            {!thinkingExpanded && (
              <span className="stream-renderer__thinking-hint">
                {streaming && !hasBody
                  ? t('agent:thinking.generating')
                  : thinkingLines > 0
                    ? t('agent:thinking.lines', { n: thinkingLines })
                    : t('agent:thinking.expand')}
              </span>
            )}
            {thinkingExpanded && (
              <span className="stream-renderer__thinking-hint">{t('agent:thinking.collapse')}</span>
            )}
          </button>
          {thinkingExpanded && (
            <pre className="stream-renderer__thinking-body" data-testid="thinking-body">
              {realThinking}
            </pre>
          )}
        </div>
      )}
      <div
        className={`stream-renderer__body${
          collapseBody ? ' stream-renderer__body--collapsed' : ''
        }`}
      >
        {hasBody ? (
          <MarkdownRenderer content={rendered} />
        ) : streaming ? (
          <p className="stream-renderer__placeholder muted">
            {hasRealThinking
              ? t('agent:thinking.organizing')
              : // Chinese keyword matching is intentional: it classifies the LLM's
                // (zh-authored) thinking text, it is functional data, not display copy
                /汇总|合并/.test(thinkingTrim)
                ? t('agent:thinking.summarizing')
                : /评估/.test(thinkingTrim)
                  ? t('agent:thinking.evaluating')
                  : t('agent:thinking.executing')}
          </p>
        ) : null}
        {streaming && hasBody && (
          <span className="stream-renderer__cursor" aria-hidden>
            ▊
          </span>
        )}
      </div>
    </div>
  );
}
