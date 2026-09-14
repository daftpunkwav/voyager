/**
 * @file TrajectoryView
 * @description Full execution-trajectory view (the 对话/轨迹 tab's second
 * pane): closed per-turn trails rebuilt from persisted rows plus the live
 * turn, rendered in execution order with 输入/模型/工具 rails, expandable
 * call details, and a per-turn cost bar (rounds, latency, tokens).
 *
 * Data comes from chatStore.trails (refresh-safe) with live steps/lastSteps
 * appended by step-seq dedup, so a refresh never loses the picture and live
 * turns keep streaming in.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toolLabel, StepTraceIcon } from '@/widgets/chat/TurnTrace';
import { StepDetail } from '@/widgets/chat/StepDetail';
import { useChatStore, type TurnStep } from '@/stores/chatStore';
import { formatCompactCount, formatDurationSec, summarizeTurn } from '@/utils/trajectory';

function fmtTotalSec(
  firstTs: number | undefined,
  lastTs: number | undefined,
  fallbackMs: number
): number {
  if (firstTs && lastTs && lastTs >= firstTs) return Math.max(0, Math.round(lastTs - firstTs));
  return Math.max(0, Math.round(fallbackMs / 1000));
}

function TurnCard({
  userText,
  steps,
  running,
  defaultOpen,
}: {
  userText: string;
  steps: TurnStep[];
  running: boolean;
  defaultOpen: boolean;
}) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(defaultOpen);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const stats = summarizeTurn(steps);
  const first = steps[0]?.ts;
  const last = steps[steps.length - 1]?.ts;
  const totalSec = fmtTotalSec(first, last, stats.ms);
  const toggle = (seq: number) => setExpanded((prev) => ({ ...prev, [seq]: !prev[seq] }));

  return (
    <section className="chat-traj__turn">
      <button
        type="button"
        className="chat-traj__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="chat-traj__query">{userText || t('chat:traj.untitledTurn')}</span>
        {running ? <span className="chat-traj__running">{t('chat:traj.running')}</span> : null}
        <span className="chat-traj__stats muted">
          {t('chat:traj.statTurn', { rounds: stats.rounds, tools: stats.toolCalls })}
          {' | '}
          {t('chat:traj.statTime', { dur: formatDurationSec(totalSec, t) })}
          {' | '}
          {t('chat:traj.statTokens', {
            a: formatCompactCount(stats.inputTokens),
            b: formatCompactCount(stats.outputTokens),
          })}
          {stats.ttftMs !== null ? ` | ${t('chat:traj.statTtft', { t: `${stats.ttftMs}ms` })}` : ''}
        </span>
        <span className="chat-traj__caret" aria-hidden>
          {open ? '▾' : '▸'}
        </span>
      </button>
      {open ? (
        <ol className="chat-traj__list">
          <li className="chat-traj__row">
            <span className="chat-traj__rail">{t('chat:traj.input')}</span>
            <span className="chat-traj__text">{userText || t('chat:traj.untitledTurn')}</span>
          </li>
          {steps.map((s) => {
            const isTool = s.kind === 'tool';
            const label = isTool ? toolLabel(s.title || s.name, t) : t('chat:proc.think');
            const show = !!expanded[s.seq];
            return (
              <li key={s.seq} className="chat-traj__row">
                <span className="chat-traj__rail">
                  {isTool ? t('chat:traj.tool') : t('chat:traj.model')}
                </span>
                <div className="chat-traj__body">
                  <button
                    type="button"
                    className="chat-traj__step"
                    aria-expanded={show}
                    aria-label={`${label} ${t('chat:traj.detailToggle')}`}
                    onClick={() => toggle(s.seq)}
                  >
                    <span className="chat-trace__rowicon" aria-hidden>
                      <StepTraceIcon step={s} />
                    </span>
                    <span className="chat-traj__label">{label}</span>
                    {s.ok === false ? (
                      <span className="chat-stepdetail__badge chat-stepdetail__badge--fail">
                        {t('chat:traj.statusFail')}
                      </span>
                    ) : null}
                    {typeof s.ms === 'number' ? <span className="muted">{s.ms}ms</span> : null}
                    {s.summary ? (
                      <span className="chat-trace__rowsummary" title={s.summary}>
                        {s.summary}
                      </span>
                    ) : null}
                    <span className="chat-traj__caret" aria-hidden>
                      {show ? '▾' : '▸'}
                    </span>
                  </button>
                  {show ? <StepDetail step={s} /> : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}

export function TrajectoryView() {
  const { t } = useTranslation('chat');
  const trails = useChatStore((s) => s.trails);
  const steps = useChatStore((s) => s.steps);
  const lastSteps = useChatStore((s) => s.lastSteps);
  const messages = useChatStore((s) => s.messages);

  // The user text opening the latest turn (for live tails without a trail).
  let latestUserText = '';
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'user' && messages[i].seq > 0) {
      latestUserText = messages[i].content;
      break;
    }
  }

  // Live tails not yet covered by a persisted trail (seq-set dedup keeps
  // refresh rebuilds and the live stream from doubling).
  const covered = new Set<number>();
  for (const trail of trails) for (const s of trail.steps) covered.add(s.seq);
  const liveLast = lastSteps.filter((s) => !covered.has(s.seq));
  const liveSteps = steps.filter((s) => !covered.has(s.seq));

  if (trails.length === 0 && liveLast.length === 0 && liveSteps.length === 0) {
    return <div className="chat-traj__empty muted">{t('chat:traj.empty')}</div>;
  }
  return (
    <div className="chat-traj">
      {trails.map((trail) => (
        <TurnCard
          key={trail.msgSeq}
          userText={trail.userText}
          steps={trail.steps}
          running={false}
          defaultOpen={false}
        />
      ))}
      {liveLast.length > 0 ? (
        <TurnCard userText={latestUserText} steps={liveLast} running={false} defaultOpen={false} />
      ) : null}
      {liveSteps.length > 0 ? (
        <TurnCard userText={latestUserText} steps={liveSteps} running defaultOpen />
      ) : null}
    </div>
  );
}
