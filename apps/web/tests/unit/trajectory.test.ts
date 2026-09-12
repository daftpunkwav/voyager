/**
 * @file trajectory
 * @description Unit tests for trajectory grouping and turn summaries:
 * per-turn regrouping, open-turn leftovers, and cost aggregation.
 */

import { describe, expect, it } from 'vitest';
import type { ChatMessage, TurnStep } from '@/stores/chatStore';
import { formatCompactCount, groupTrails, summarizeTurn } from '@/utils/trajectory';

function msg(seq: number, role: ChatMessage['role'], content = ''): ChatMessage {
  return { seq, role, content };
}

function step(seq: number, kind: string, extra: Partial<TurnStep> = {}): TurnStep {
  return {
    seq,
    kind,
    name: kind === 'tool' ? 'read_file' : 'round-1',
    summary: '',
    subagent: 'chat',
    ...extra,
  };
}

describe('groupTrails', () => {
  it('groups steps under their closing agent message', () => {
    const messages = [
      msg(1, 'user', 'hi'),
      msg(4, 'agent', 'done'),
      msg(5, 'user', 'thx'),
      msg(8, 'agent', 'yw'),
    ];
    const steps = [step(2, 'llm'), step(3, 'tool'), step(6, 'llm'), step(7, 'tool')];
    const { trails, openSteps } = groupTrails(messages, steps);
    expect(trails).toHaveLength(2);
    expect(trails[0]).toMatchObject({ msgSeq: 4, userText: 'hi' });
    expect(trails[0].steps.map((s) => s.seq)).toEqual([2, 3]);
    expect(trails[1].steps.map((s) => s.seq)).toEqual([6, 7]);
    expect(openSteps).toEqual([]);
  });

  it('leaves post-message steps open and skips empty turns', () => {
    const messages = [msg(1, 'user', 'hi'), msg(2, 'agent', 'ok'), msg(3, 'user', 'more')];
    const steps = [step(4, 'llm')];
    const { trails, openSteps } = groupTrails(messages, steps);
    expect(trails).toEqual([]);
    expect(openSteps.map((s) => s.seq)).toEqual([4]);
  });

  it('sorts unsorted inputs and ignores transient local messages', () => {
    const messages = [msg(4, 'agent', 'done'), msg(-1, 'user', 'draft'), msg(1, 'user', 'hi')];
    const steps = [step(3, 'tool'), step(2, 'llm')];
    const { trails } = groupTrails(messages, steps);
    expect(trails).toHaveLength(1);
    expect(trails[0].steps.map((s) => s.seq)).toEqual([2, 3]);
  });

  it('a step sharing the message seq stays open (strict-less ownership)', () => {
    const messages = [msg(1, 'user', 'hi'), msg(4, 'agent', 'done')];
    const steps = [step(2, 'llm'), step(4, 'tool')];
    const { trails, openSteps } = groupTrails(messages, steps);
    expect(trails[0].steps.map((s) => s.seq)).toEqual([2]);
    expect(openSteps.map((s) => s.seq)).toEqual([4]);
  });

  it('non-finite numbers never poison sums', () => {
    const stats = summarizeTurn([step(1, 'llm', { round: 1, ms: NaN, inputTokens: NaN })]);
    expect(stats.ms).toBe(0);
    expect(stats.inputTokens).toBe(0);
  });
});

describe('summarizeTurn', () => {
  it('aggregates rounds, tools, latency and tokens', () => {
    const stats = summarizeTurn([
      step(1, 'llm', { round: 1, ms: 1200, inputTokens: 100, outputTokens: 20, ttftMs: 300 }),
      step(2, 'tool', { ms: 50 }),
      step(3, 'llm', { round: 2, ms: 800, inputTokens: 200, outputTokens: 40, ttftMs: 500 }),
      step(4, 'tool', { ms: 30 }),
    ]);
    expect(stats).toMatchObject({
      rounds: 2,
      toolCalls: 2,
      ms: 2080,
      inputTokens: 300,
      outputTokens: 60,
    });
    expect(stats.ttftMs).toBe(400);
  });

  it('ttft is null without streamed rounds', () => {
    expect(summarizeTurn([step(1, 'llm', { round: 1 })]).ttftMs).toBeNull();
  });
});

describe('formatCompactCount', () => {
  it('formats counts compactly', () => {
    expect(formatCompactCount(999)).toBe('999');
    expect(formatCompactCount(33600)).toBe('33.6k');
    expect(formatCompactCount(33000)).toBe('33k');
  });
});
