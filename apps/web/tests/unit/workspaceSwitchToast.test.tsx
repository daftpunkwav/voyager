/**
 * @file workspaceSwitchToast
 * @description workspace.switched cross-tab notice unit tests: the event
 * fires an info toast and bumps the workspace revision for views to refetch,
 * and never enters the chat timeline.
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
import { initI18n } from '@/i18n';

/** Probe component that mounts the hook (onNavigate is unused here) */
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
  useChatStore.setState({ messages: [], workspaceRev: 0 });
  useUIStore.setState({ toasts: [] });
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ json: async () => ({ messages: [] }) } as Response)
  );
  initI18n();
});

describe('workspace.switched → toast + revision bump', () => {
  it('toasts once, bumps workspaceRev, keeps the timeline clean', () => {
    render(<HookProbe />);
    handler()({ seq: 1, type: 'workspace.switched', payload: { workspace: 'ws2' } });
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('info');
    expect(useChatStore.getState().workspaceRev).toBe(1);
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it('repeated switches keep bumping the revision', () => {
    render(<HookProbe />);
    handler()({ seq: 1, type: 'workspace.switched', payload: { workspace: 'a' } });
    handler()({ seq: 2, type: 'workspace.switched', payload: { workspace: 'b' } });
    expect(useChatStore.getState().workspaceRev).toBe(2);
  });
});
