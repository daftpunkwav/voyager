/**
 * @file chatTrajectory
 * @description chatStore trajectory tests: persisted step backfill regroups
 * closed turns, live agent.message appends idempotent trails, and step
 * payloads map to TurnStep detail fields.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useChatStore, type ChatEvent } from '@/stores/chatStore';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
}

function reset() {
  seq = 0;
  useChatStore.setState({
    messages: [],
    hasMoreHistory: false,
    historyLoading: false,
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    connected: true,
    thinking: false,
    currentStep: null,
    steps: [],
    trails: [],
    lastSteps: [],
    streaming: null,
  });
}

beforeEach(reset);

describe('trajectory backfill', () => {
  it('applyTrajectory regroups persisted steps under messages', () => {
    useChatStore.getState().applyHistory([
      { seq: 1, type: 'user.message', payload: { content: 'hi' } },
      { seq: 4, type: 'agent.message', payload: { content: 'done' } },
    ] as ChatEvent[]);
    useChatStore.getState().applyTrajectory([
      {
        seq: 2,
        type: 'agent.step',
        payload: {
          kind: 'llm',
          name: 'round-1',
          summary: 't',
          subagent: 'chat',
          detail: { round: 1, ms: 100 },
        },
      },
      {
        seq: 3,
        type: 'agent.step',
        payload: {
          kind: 'tool',
          name: 'read_file',
          summary: 'r',
          subagent: 'chat',
          run_id: 'r1',
          detail: { tool_call_id: 'c-1', args: '{"path":"a"}', ok: true, ms: 12 },
        },
      },
    ] as ChatEvent[]);
    const { trails, steps } = useChatStore.getState();
    expect(trails).toHaveLength(1);
    expect(trails[0]).toMatchObject({ msgSeq: 4, userText: 'hi' });
    expect(trails[0].steps).toHaveLength(2);
    expect(trails[0].steps[1]).toMatchObject({ toolCallId: 'c-1', ok: true, ms: 12, runId: 'r1' });
    expect(steps).toEqual([]);
  });

  it('live agent.message appends an idempotent trail', () => {
    dispatch('agent.step', { kind: 'tool', name: 'read_file', summary: 'r', subagent: 'chat' });
    dispatch('agent.message', { content: 'done' });
    const first = useChatStore.getState().trails;
    expect(first).toHaveLength(1);
    expect(first[0].steps).toHaveLength(1);
    // A redelivered backfill of the same turn upserts instead of duplicating
    useChatStore.getState().applyTrajectory([
      {
        seq: 1,
        type: 'agent.step',
        payload: { kind: 'tool', name: 'read_file', summary: 'r', subagent: 'chat' },
      },
    ] as ChatEvent[]);
    expect(useChatStore.getState().trails).toHaveLength(1);
  });

  it('an interrupted turn survives later empty turns in trails', () => {
    dispatch('agent.step', { kind: 'tool', name: 'read_file', summary: 'r', subagent: 'chat' });
    useChatStore.getState().clearThinking();
    expect(useChatStore.getState().trails).toHaveLength(1);
    expect(useChatStore.getState().trails[0].steps).toHaveLength(1);
    // A later plain answer carries no steps: the interrupted trail stays,
    // the collapsed timeline simply goes quiet.
    dispatch('agent.message', { content: 'ok' });
    expect(useChatStore.getState().trails).toHaveLength(1);
    expect(useChatStore.getState().lastSteps).toEqual([]);
  });

  it('null payloads map to empty steps, never throw', () => {
    expect(() =>
      useChatStore
        .getState()
        .applyTrajectory([{ seq: 1, type: 'agent.step', payload: null }] as unknown as ChatEvent[])
    ).not.toThrow();
  });

  it('agent.message kind error survives into the message', () => {
    dispatch('agent.message', { content: '(LLM call failed: boom)', kind: 'error' });
    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({ role: 'agent', kind: 'error' });
    dispatch('agent.message', { content: 'ok' });
    expect(useChatStore.getState().messages[1].kind).toBeUndefined();
  });

  it('history backfill carries message kind and step reasoning', () => {
    useChatStore.getState().applyHistory([
      { seq: 1, type: 'user.message', payload: { content: 'hi' } },
      { seq: 4, type: 'agent.message', payload: { content: 'boom', kind: 'error' } },
    ] as ChatEvent[]);
    expect(useChatStore.getState().messages[1]).toMatchObject({ kind: 'error' });
    useChatStore.getState().applyTrajectory([
      {
        seq: 2,
        type: 'agent.step',
        payload: {
          kind: 'llm',
          name: 'round-1',
          summary: 't',
          subagent: 'chat',
          detail: { round: 1, reasoning: 'weigh options' },
        },
      },
    ] as ChatEvent[]);
    expect(useChatStore.getState().trails[0].steps[0]).toMatchObject({
      reasoning: 'weigh options',
    });
  });
});
