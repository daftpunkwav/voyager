/**
 * @file policyNotifyToast
 * @description L1 policy-notify toast unit tests (phase-40 §9.9):
 * agent.policy.notify only fires an info toast and never enters the chat
 * timeline; a blank message fires nothing; all other events still go through
 * chatStore.dispatch.
 */

import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { subscribeMock } = vi.hoisted(() => ({
  subscribeMock: vi.fn(() => () => {}),
}));

vi.mock('@/bridge/stream', () => ({ subscribe: subscribeMock }));

import { useChatStream } from '@/hooks/useChatStream';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';

/** Probe component that mounts the hook (onNavigate is unused at this phase) */
function HookProbe() {
  useChatStream(() => {});
  return null;
}

/** Captures the event callback that useChatStream registers into subscribe */
function handler() {
  return subscribeMock.mock.calls[0][1] as (ev: {
    seq: number;
    type: string;
    payload: Record<string, unknown>;
  }) => void;
}

beforeEach(() => {
  subscribeMock.mockClear();
  useChatStore.setState({ messages: [] });
  useUIStore.setState({ toasts: [] });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ json: async () => ({ messages: [] }) } as Response)
  );
});

describe('agent.policy.notify → toast(phase-40)', () => {
  it('shows an info toast on the event and keeps the message out of the timeline', () => {
    render(<HookProbe />);
    handler()({ seq: 1, type: 'agent.policy.notify', payload: { message: 'write_file: g.txt' } });
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('info');
    expect(toasts[0].message).toBe('write_file: g.txt');
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it('does not show a toast when message is blank', () => {
    render(<HookProbe />);
    handler()({ seq: 2, type: 'agent.policy.notify', payload: { message: '   ' } });
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });

  it('still dispatches other events into chatStore as before (regression)', () => {
    render(<HookProbe />);
    handler()({
      seq: 3,
      type: 'agent.step',
      payload: { kind: 'tool', name: 'read_file', summary: 'ok', subagent: 'chat' },
    });
    expect(useUIStore.getState().toasts).toHaveLength(0);
    expect(useChatStore.getState().steps).toHaveLength(1);
    expect(useChatStore.getState().currentStep?.name).toBe('read_file');
  });
});
