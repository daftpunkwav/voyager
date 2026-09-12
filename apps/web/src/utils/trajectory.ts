/**
 * @file trajectory
 * @description Pure helpers for the execution-trajectory view: group persisted
 * steps back into per-turn trails and summarize one turn's cost.
 *
 * A trail closes at the first agent.message after its steps (steps are
 * emitted during the turn, the message ends it). Steps past the last agent
 * message belong to the still-open turn. Grouping is seq-ordered and
 * idempotent, so history backfills and live SSE appends compose.
 *
 * This module must not depend on UI-layer components or stores (only types).
 */

import type { ChatMessage, TurnStep, TurnTrail } from '@/stores/chatStore';

export interface GroupedTrails {
  trails: TurnTrail[];
  /** Steps past the last agent.message (the still-open turn). */
  openSteps: TurnStep[];
}

/** Group steps into per-turn trails following message order. Both inputs
 *  may arrive unsorted; output trails ascend by msgSeq.
 *
 *  Ownership is strict-less (step.seq < msg.seq): backend seqs grow
 *  monotonically, so equality only occurs on redelivery, which stays open.
 *  Consecutive user messages keep the last text (the turn's effective
 *  prompt); transient local echoes (seq < 0) are not anchors. */
export function groupTrails(messages: ChatMessage[], steps: TurnStep[]): GroupedTrails {
  const ordered = [...messages].sort((a, b) => a.seq - b.seq);
  const pending = [...steps].sort((a, b) => a.seq - b.seq);
  const trails: TurnTrail[] = [];
  let userText = '';
  let cursor = 0;
  for (const msg of ordered) {
    if (msg.seq < 0) continue; // transient local echoes are not grouping anchors
    if (msg.role === 'user') {
      if (msg.content) userText = msg.content;
      continue;
    }
    if (msg.role !== 'agent') continue;
    const owned = pending.slice(cursor, cursor + cursorCount(pending, cursor, msg.seq));
    cursor += owned.length;
    if (owned.length > 0) {
      trails.push({ msgSeq: msg.seq, userText, steps: owned });
    }
    userText = '';
  }
  return { trails, openSteps: pending.slice(cursor) };
}

/** Count of steps from index `from` with seq below `below` (inputs sorted). */
function cursorCount(sorted: TurnStep[], from: number, below: number): number {
  let n = 0;
  for (let i = from; i < sorted.length; i++) {
    if (sorted[i].seq >= below) break;
    n++;
  }
  return n;
}

/** Per-turn cost totals for the stats bar. */
export interface TurnStats {
  rounds: number;
  toolCalls: number;
  ms: number;
  inputTokens: number;
  outputTokens: number;
  /** Mean first-token latency over streamed rounds; null when none streamed. */
  ttftMs: number | null;
}

export function summarizeTurn(steps: TurnStep[]): TurnStats {
  let rounds = 0;
  let toolCalls = 0;
  let ms = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  let ttftSum = 0;
  let ttftN = 0;
  const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  for (const s of steps) {
    if (s.kind === 'tool') toolCalls++;
    if (s.round !== undefined) rounds++;
    if (finite(s.ms)) ms += s.ms;
    if (finite(s.inputTokens)) inputTokens += s.inputTokens;
    if (finite(s.outputTokens)) outputTokens += s.outputTokens;
    if (finite(s.ttftMs)) {
      ttftSum += s.ttftMs;
      ttftN++;
    }
  }
  return {
    rounds,
    toolCalls,
    ms: Math.round(ms),
    inputTokens,
    outputTokens,
    ttftMs: ttftN ? Math.round((ttftSum / ttftN) * 10) / 10 : null,
  };
}

/** Compact token count: 999 -> "999", 33600 -> "33.6k", 33000 -> "33k". */
export function formatCompactCount(n: number): string {
  if (!Number.isFinite(n) || n < 1000) return String(Math.max(0, Math.floor(n || 0)));
  const k = n / 1000;
  const text = k >= 100 ? String(Math.round(k)) : k.toFixed(1);
  return `${text.replace(/\.0$/, '')}k`;
}

/** Seconds -> localized duration reusing the proc.* keys (shared by the
 *  timeline and the trajectory view so the two never drift). */
export function formatDurationSec(
  sec: number,
  t: (k: string, o?: Record<string, unknown>) => string
): string {
  if (sec < 60) return t('chat:proc.seconds', { n: sec });
  const m = Math.floor(sec / 60);
  const rest = sec % 60;
  return rest ? t('chat:proc.minSec', { m, n: rest }) : t('chat:proc.minutes', { m });
}
