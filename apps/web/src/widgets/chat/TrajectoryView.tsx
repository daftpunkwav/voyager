/**
 * @file TrajectoryView
 * @description Full execution-trajectory page, localized from DSH's
 * ui-trajectory: a stats toolbar (duration / turns / calls + search), a
 * three-lane timeline (input / model / tools) where every event is a span
 * that scrolls the table to its row, and a turn-grouped event table whose
 * rows expand in place (tool call details, full reasoning text, assistant
 * output).
 *
 * Data comes from chatStore: trails (persisted per-turn steps), live steps,
 * and the message stream. Rows are derived, never persisted.
 */

import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toolLabel } from '@/widgets/chat/TurnTrace';
import { StepDetail } from '@/widgets/chat/StepDetail';
import { type ChatMessage, type TurnTrail, useChatStore, type TurnStep } from '@/stores/chatStore';
import { formatCompactCount, formatDurationSec, summarizeTurn } from '@/utils/trajectory';

type RowKind = 'user' | 'assistant' | 'think' | 'tool' | 'op';

interface TrajRow {
  key: string;
  kind: RowKind;
  turn: number;
  label: string;
  text: string;
  step?: TurnStep;
  ts?: number;
}

const KIND_LABEL_KEYS: Record<RowKind, string> = {
  user: 'chat:traj.badgeUser',
  assistant: 'chat:traj.badgeAssistant',
  think: 'chat:traj.badgeThink',
  tool: 'chat:traj.badgeTool',
  op: 'chat:traj.badgeOp',
};

const LANES: Array<{ key: RowKind[]; labelKey: string }> = [
  { key: ['user'], labelKey: 'chat:traj.laneInput' },
  { key: ['think', 'assistant'], labelKey: 'chat:traj.laneModel' },
  { key: ['tool', 'op'], labelKey: 'chat:traj.laneTools' },
];

function laneFor(kind: RowKind): number {
  return LANES.findIndex((l) => l.key.includes(kind));
}

/** Build the flat event rows from the store: every user message opens a
 *  turn; its trail steps (reasoning/tools/ops) precede the assistant reply. */
function buildRows(
  messages: ChatMessage[],
  trails: TurnTrail[],
  liveSteps: TurnStep[],
  t: (k: string, o?: Record<string, unknown>) => string
): TrajRow[] {
  const trailBySeq = new Map(trails.map((tr) => [tr.msgSeq, tr]));
  const rows: TrajRow[] = [];
  let turn = 0;
  const pushSteps = (steps: TurnStep[], keyPrefix: string) => {
    for (const s of steps) {
      if (s.kind === 'llm') {
        rows.push({
          key: `${keyPrefix}-think-${s.seq}`,
          kind: 'think',
          turn,
          label: t('chat:proc.think'),
          text: s.text || s.summary,
          step: s,
          ts: s.ts,
        });
      } else if (s.kind === 'system') {
        rows.push({
          key: `${keyPrefix}-op-${s.seq}`,
          kind: 'op',
          turn,
          label: t(`chat:op.${s.name}`, { defaultValue: s.name }),
          text: s.summary,
          step: s,
          ts: s.ts,
        });
      } else {
        rows.push({
          key: `${keyPrefix}-tool-${s.seq}`,
          kind: 'tool',
          turn,
          label: toolLabel(s.title || s.name, t),
          text: s.summary,
          step: s,
          ts: s.ts,
        });
      }
    }
  };

  const closedSeqs = new Set<number>();
  for (const tr of trails) for (const s of tr.steps) closedSeqs.add(s.seq);

  for (const m of messages) {
    if (m.role === 'user') {
      if (!m.content) continue;
      turn += 1;
      rows.push({
        key: `u-${m.seq}`,
        kind: 'user',
        turn,
        label: t('chat:traj.badgeUser'),
        text: m.content,
        ts: m.ts,
      });
      continue;
    }
    if (m.role !== 'agent') continue;
    const trail = trailBySeq.get(m.seq);
    if (trail) pushSteps(trail.steps, `t${m.seq}`);
    rows.push({
      key: `a-${m.seq}`,
      kind: 'assistant',
      turn: Math.max(turn, 1),
      label: t('chat:traj.badgeAssistant'),
      text: m.content,
      ts: m.ts,
    });
  }
  // Live turn: steps not yet covered by a closed trail.
  const live = liveSteps.filter((s) => !closedSeqs.has(s.seq));
  if (live.length > 0) {
    turn += 1;
    pushSteps(live, 'live');
  }
  return rows;
}

export function TrajectoryView() {
  const { t } = useTranslation('chat');
  const trails = useChatStore((s) => s.trails);
  const steps = useChatStore((s) => s.steps);
  const lastSteps = useChatStore((s) => s.lastSteps);
  const messages = useChatStore((s) => s.messages);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const tableRef = useRef<HTMLDivElement>(null);

  const allSteps = [...trails.flatMap((tr) => tr.steps), ...steps, ...lastSteps];
  const stats = summarizeTurn(allSteps);
  const firstTs = allSteps[0]?.ts;
  const lastTs = allSteps[allSteps.length - 1]?.ts;
  const totalSec = firstTs && lastTs ? Math.max(0, Math.round(lastTs - firstTs)) : 0;

  const rows = useMemo(
    () => buildRows(messages, trails, steps, t),
    [messages, trails, steps, t]
  );

  const filtered = query.trim()
    ? rows.filter((r) => r.text.toLowerCase().includes(query.trim().toLowerCase()))
    : rows;

  const scrollToRow = (key: string) => {
    setSelected(key);
    const el = tableRef.current?.querySelector(`[data-row-key="${CSS.escape(key)}"]`);
    el?.scrollIntoView({ block: 'center', behavior: 'auto' });
  };

  if (rows.length === 0) {
    return <div className="chat-traj__empty muted">{t('chat:traj.empty')}</div>;
  }

  return (
    <div className="chat-traj2">
      <div className="chat-traj2__toolbar">
        <span className="chat-traj2__stat">{t('chat:traj.statsDuration', { v: formatDurationSec(totalSec, t) })}</span>
        <span className="chat-traj2__stat">{t('chat:traj.statsTurns', { n: rows.filter((r) => r.kind === 'user').length })}</span>
        <span className="chat-traj2__stat">{t('chat:traj.statsCalls', { n: stats.toolCalls })}</span>
        <span className="chat-traj2__stat muted">
          {t('chat:traj.statsTokens', {
            a: formatCompactCount(stats.inputTokens),
            b: formatCompactCount(stats.outputTokens),
          })}
        </span>
        <input
          className="field input chat-traj2__search"
          placeholder={t('chat:traj.searchPlaceholder')}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="chat-traj2__timeline" role="img" aria-label={t('chat:traj.timelineAria')}>
        <div className="chat-traj2__lanes">
          {LANES.map((l) => (
            <span key={l.labelKey} className="chat-traj2__lane-label">
              {t(l.labelKey)}
            </span>
          ))}
        </div>
        <div className="chat-traj2__spans">
          {filtered.map((r, i) => (
            <span
              key={r.key}
              className={`chat-traj2__span is-${r.kind}${selected === r.key ? ' is-selected' : ''}`}
              style={{
                left: `${(i / Math.max(filtered.length, 1)) * 100}%`,
                width: `${100 / Math.max(filtered.length, 1)}%`,
                top: `${laneFor(r.kind) * 16}px`,
              }}
              title={r.text.slice(0, 120)}
              onClick={() => scrollToRow(r.key)}
            />
          ))}
        </div>
      </div>

      <div className="chat-traj2__table" ref={tableRef}>
        {filtered.map((r) => {
          const open = !!expanded[r.key];
          return (
            <div
              key={r.key}
              data-row-key={r.key}
              className={`chat-traj2__row${selected === r.key ? ' is-selected' : ''}`}
            >
              <button
                type="button"
                className="chat-traj2__rowhead"
                aria-expanded={open}
                onClick={() => {
                  setExpanded((prev) => ({ ...prev, [r.key]: !prev[r.key] }));
                  setSelected(r.key);
                }}
              >
                <span className={`chat-traj2__badge is-${r.kind}`}>{t(KIND_LABEL_KEYS[r.kind])}</span>
                <span className="chat-traj2__rowtext">
                  {r.kind === 'tool' || r.kind === 'op'
                    ? `${r.label}${r.text ? ` ${r.text}` : ''}`
                    : r.text || r.label}
                </span>
              </button>
              {open && r.step ? (
                <div className="chat-traj2__detail">
                  <StepDetail step={r.step} />
                </div>
              ) : null}
              {open && !r.step && r.kind === 'assistant' ? (
                <div className="chat-traj2__detail chat-md">
                  <div>{r.text}</div>
                </div>
              ) : null}
              {open && !r.step && r.kind === 'user' ? (
                <div className="chat-traj2__detail chat-md">
                  <div>{r.text}</div>
                </div>
              ) : null}
            </div>
          );
        })}
        {filtered.length === 0 ? (
          <div className="chat-traj2__empty muted">{t('chat:traj.searchEmpty')}</div>
        ) : null}
      </div>
    </div>
  );
}
