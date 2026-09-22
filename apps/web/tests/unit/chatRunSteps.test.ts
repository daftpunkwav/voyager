/**
 * @file chatRunSteps
 * @description The subagent execution view's data slice: hydrateRunSteps
 * seeds one run's step log from /api/chat/trajectory?run_id, the live
 * AGENT_STEP dispatch mirrors into it, and the caps (RUN_STEPS_CAP /
 * RUNS_CAP) keep a long-lived tab from accumulating every finished run's
 * full trail forever.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { EventType } from '@/bridge/events';
import { toTurnStep, useChatStore } from '@/stores/chatStore';
import type { ChatEvent, TurnStep } from '@/stores/chatStore';

function stepEvent(seq: number, runId: string, name = 'write'): ChatEvent {
  return {
    seq,
    type: EventType.AGENT_STEP,
    payload: { run_id: runId, kind: 'tool', name, session: '' },
    ts: 1,
  };
}

describe('hydrateRunSteps', () => {
  beforeEach(() => {
    useChatStore.setState({ runSteps: {}, steps: [], messages: [] });
  });

  it('seeds one run’s log from agent.step rows only, ascending by seq', () => {
    useChatStore.getState().hydrateRunSteps('r1', [
      { seq: 3, type: EventType.AGENT_STEP, payload: { run_id: 'r1', kind: 'tool', name: 'b' }, ts: 1 },
      { seq: 1, type: EventType.AGENT_STEP, payload: { run_id: 'r1', kind: 'llm', name: 'round-1' }, ts: 1 },
      { seq: 2, type: EventType.AGENT_MESSAGE, payload: { content: 'not a step' }, ts: 1 },
    ]);
    const steps = useChatStore.getState().runSteps.r1;
    expect(steps.map((s) => s.seq)).toEqual([1, 3]);
    expect(steps[0].name).toBe('round-1');
  });

  it('drops rows whose own run_id disagrees with the requested run', () => {
    // The API narrows by run_id, but a row stamped for another run (stale
    // fetch racing a re-open) must never land under the wrong run's key.
    useChatStore.getState().hydrateRunSteps('r1', [
      stepEvent(1, 'r1'),
      stepEvent(2, 'r2'),
    ]);
    expect(useChatStore.getState().runSteps.r1.map((s) => s.seq)).toEqual([1]);
  });

  it('is idempotent by seq: re-hydrating overlapping pages never duplicates', () => {
    const page = [stepEvent(1, 'r1'), stepEvent(2, 'r1')];
    useChatStore.getState().hydrateRunSteps('r1', page);
    useChatStore.getState().hydrateRunSteps('r1', [stepEvent(2, 'r1'), stepEvent(3, 'r1')]);
    expect(useChatStore.getState().runSteps.r1.map((s) => s.seq)).toEqual([1, 2, 3]);
  });

  it('ignores an empty run id instead of writing a "" bucket', () => {
    useChatStore.getState().hydrateRunSteps('', [stepEvent(1, '')]);
    expect(useChatStore.getState().runSteps).toEqual({});
  });

  it('trims a run past RUN_STEPS_CAP to the newest 800 steps', () => {
    const page = Array.from({ length: 810 }, (_, i) => stepEvent(i + 1, 'r1'));
    useChatStore.getState().hydrateRunSteps('r1', page);
    const steps = useChatStore.getState().runSteps.r1;
    expect(steps).toHaveLength(800);
    expect(steps[0].seq).toBe(11); // the head was dropped, the tail survived
    expect(steps[799].seq).toBe(810);
  });

  it('evicts the oldest runs past RUNS_CAP, the newly hydrated one survives', () => {
    // 50 pre-existing runs, earliest step seq rising with the run index
    const prefilled: Record<string, TurnStep[]> = {};
    for (let i = 0; i < 50; i += 1) {
      prefilled[`run${i}`] = [stepEvent(i * 10, `run${i}`)].map(toTurnStep);
    }
    useChatStore.setState({ runSteps: prefilled });
    useChatStore.getState().hydrateRunSteps('run-new', [stepEvent(999, 'run-new')]);
    const runSteps = useChatStore.getState().runSteps;
    expect(Object.keys(runSteps)).toHaveLength(50); // back under the cap
    expect(runSteps.run0).toBeUndefined(); // earliest seq -> evicted first
    expect(runSteps['run-new']).toHaveLength(1); // the active run survives
    expect(runSteps.run49).toHaveLength(1);
  });
});

describe('dispatch mirrors live AGENT_STEP into runSteps', () => {
  beforeEach(() => {
    useChatStore.setState({ runSteps: {}, steps: [], messages: [], currentStep: null });
  });

  it('appends the step under its run_id and dedups SSE replays', () => {
    useChatStore.getState().dispatch(stepEvent(7, 'r1'));
    useChatStore.getState().dispatch(stepEvent(7, 'r1'));
    expect(useChatStore.getState().runSteps.r1.map((s) => s.seq)).toEqual([7]);
    expect(useChatStore.getState().steps.map((s) => s.seq)).toEqual([7]);
  });

  it('session-less steps without a run_id never create a runSteps entry', () => {
    useChatStore.getState().dispatch({
      seq: 8,
      type: EventType.AGENT_STEP,
      payload: { kind: 'tool', name: 'grep' },
      ts: 1,
    });
    expect(useChatStore.getState().runSteps).toEqual({});
    expect(useChatStore.getState().steps).toHaveLength(1); // timeline still grows
  });
});
