/**
 * @file policyNotifyToast
 * @description agent.policy.notify is no longer surfaced: batch operations
 * fired one toast per write call and flooded the chat page. The event must
 * neither raise a toast nor enter the chat timeline; other events still go
 * through chatStore.dispatch.
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

describe('agent.policy.notify stays silent (operations live in the activity page)', () => {
  it('raises no toast and keeps the message out of the timeline', () => {
    render(<HookProbe />);
    handler()({ seq: 1, type: 'agent.policy.notify', payload: { message: 'session: session' } });
    expect(useUIStore.getState().toasts).toHaveLength(0);
    expect(useChatStore.getState().messages).toHaveLength(0);
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
