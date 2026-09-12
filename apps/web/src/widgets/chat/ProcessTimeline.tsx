/**
 * @file ProcessTimeline
 * @description Execution-trajectory panel for the chat: the running turn's steps
 * (ReAct rounds, tool calls) stay expanded; when the turn ends the trajectory
 * folds into lastSteps and collapses to a one-line summary the user can reopen.
 *
 * Data is live-only (agent.step SSE -> chatStore.steps/lastSteps): a refresh
 * rebuilds messages but not steps, matching the expand-while-running semantics.
 * Shared by the chat page and the floating window.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type TurnStep, useChatStore } from '@/stores/chatStore';
import { formatDurationSec } from '@/utils/trajectory';
import { StepDetail } from '@/widgets/chat/StepDetail';

/** Humanize a tool identifier for display: `notes__create_note` maps to the
 *  localized action label (chat:tool.create_note, e.g. "创建笔记"/"Create note");
 *  unknown capabilities fall back to the bare capability name with underscores
 *  spaced out. The raw domain__capability name stays internal on purpose: it is
 *  the namespace separator the activation/allow-list mechanics parse. */
export function toolLabel(
  name: string,
  t: (key: string, opts?: Record<string, unknown>) => string
): string {
  const idx = name.indexOf('__');
  const cap = idx >= 0 ? name.slice(idx + 2) : name;
  return t(`chat:tool.${cap}`, { defaultValue: cap.replace(/_/g, ' ') });
}

/** Row duration = gap to the next step's ts; the running tail has no next yet. */
function stepSeconds(step: TurnStep, next?: TurnStep): number | null {
  if (!step.ts || !next?.ts) return null;
  const sec = Math.round(next.ts - step.ts);
  return sec >= 0 ? sec : null;
}

export function ProcessTimeline() {
  const { t } = useTranslation('chat');
  const steps = useChatStore((s) => s.steps);
  const lastSteps = useChatStore((s) => s.lastSteps);
  const stepsOpen = useChatStore((s) => s.stepsOpen);
  const toggleSteps = useChatStore((s) => s.toggleSteps);
  // Per-row call-detail expansion (collapsed by default; kept across toggles).
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const live = steps.length > 0;
  const items = live ? steps : lastSteps;
  if (items.length === 0) return null;
  // While running the trajectory stays expanded; after the turn it collapses
  // unless the user reopened it.
  const open = live || stepsOpen;

  const tools = items.filter((s) => s.kind === 'tool').length;
  const first = items[0]?.ts;
  const last = items[items.length - 1]?.ts;
  const totalSec = first && last ? Math.max(0, Math.round(last - first)) : 0;

  return (
    <div className={`chat-proc${open ? ' chat-proc--open' : ''}`}>
      <button
        type="button"
        className="chat-proc__head small muted"
        aria-expanded={open}
        onClick={() => toggleSteps(!open)}
      >
        {open
          ? t('chat:proc.title')
          : t('chat:proc.done', {
              steps: items.length,
              tools,
              dur: formatDurationSec(totalSec, t),
            })}
        <span className="chat-proc__caret" aria-hidden>
          {open ? '▾' : '▸'}
        </span>
      </button>
      {open ? (
        <ul className="chat-proc__list small">
          {items.map((s, i) => {
            const dur = stepSeconds(s, items[i + 1]);
            const label = s.kind === 'tool' ? toolLabel(s.name, t) : t('chat:proc.think');
            const show = !!expanded[s.seq];
            return (
              <li key={s.seq} className={`chat-proc__row chat-proc__row--${s.kind || 'llm'}`}>
                <button
                  type="button"
                  className="chat-proc__expand"
                  aria-expanded={show}
                  aria-label={`${label} ${t('chat:traj.detailToggle')}`}
                  onClick={() => setExpanded((prev) => ({ ...prev, [s.seq]: !prev[s.seq] }))}
                >
                  <span className="chat-proc__icon" aria-hidden>
                    {s.kind === 'tool' ? '▪' : '✦'}
                  </span>
                  <span className="chat-proc__label">{label}</span>
                  {dur !== null ? (
                    <span className="chat-proc__dur muted">{formatDurationSec(dur, t)}</span>
                  ) : null}
                  {s.summary ? (
                    <span className="chat-proc__summary muted" title={s.summary}>
                      {s.summary}
                    </span>
                  ) : null}
                  <span className="chat-proc__caret" aria-hidden>
                    {show ? '▾' : '▸'}
                  </span>
                </button>
                {show ? <StepDetail step={s} /> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
