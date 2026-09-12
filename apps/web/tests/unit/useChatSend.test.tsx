/**
 * @file useChatSend
 * @description useChatSend quota guard unit tests (phase-67): a full quota
 * rejects the send (postChatMessage not called, draft preserved, error
 * toast), ≥80% shows a warning toast only once per session, and unlimited
 * sends as usual.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchQuotaGuardMock, postChatMessageMock } = vi.hoisted(() => ({
  fetchQuotaGuardMock: vi.fn(),
  postChatMessageMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  postChatMessage: postChatMessageMock,
}));

vi.mock('@/bridge/quotaGuard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/quotaGuard')>()),
  fetchQuotaGuard: fetchQuotaGuardMock,
}));

vi.mock('@/hooks/useLlmAvailable', () => ({
  useLlmAvailable: () => 'ok',
}));

import { useChatSend } from '@/hooks/useChatSend';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

function resetStores() {
  useUIStore.setState({ toasts: [] });
  useChatStore.setState({
    messages: [],
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
  });
}

beforeEach(() => {
  resetStores();
  fetchQuotaGuardMock.mockReset();
  postChatMessageMock.mockReset();
});

beforeAll(() => {
  // hook copy moved to the chat ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
  initI18n();
});

describe('useChatSend quota guard (phase-67)', () => {
  it('full quota block: postChatMessage not called, draft preserved, error toast', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'block', reason: 'quota exhausted' });
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('  look it up  '));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).not.toHaveBeenCalled();
    expect(result.current.draft).toBe('  look it up  ');
    expect(result.current.sending).toBe(false);
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('error');
    expect(toasts[0].message).toBe('quota exhausted');
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it('≥80% warn: sends as usual + warning toast; a second send in the same session does not warn again', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'warn', ratio: 0.85 });
    postChatMessageMock.mockResolvedValue(42);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('first'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledWith('first', undefined);
    expect(result.current.draft).toBe('');
    let toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('warning');
    expect(toasts[0].message).toContain('85%');
    expect(useChatStore.getState().messages[0]).toEqual({
      seq: 42,
      role: 'user',
      content: 'first',
    });

    // the first send set thinking=true (appendLocal); simulate the turn ending
    // (agent.message / hard stop) before the second send, as in real usage
    act(() => {
      useChatStore.setState({ thinking: false });
    });
    act(() => result.current.setDraft('second'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledTimes(2);
    toasts = useUIStore.getState().toasts;
    expect(toasts.filter((t) => t.type === 'warning')).toHaveLength(1);
  });

  it('unlimited (allow) sends as usual with no toast', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
    postChatMessageMock.mockResolvedValue(7);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('just chatting'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).toHaveBeenCalledWith('just chatting', undefined);
    expect(useUIStore.getState().toasts).toEqual([]);
    expect(useChatStore.getState().messages[0]?.seq).toBe(7);
  });

  it('agent running (thinking): send is a no-op — the composer button is the stop button then', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
    postChatMessageMock.mockResolvedValue(8);
    useChatStore.setState({ thinking: true });
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('queued mid-run?'));
    await act(async () => {
      await result.current.send();
    });

    expect(postChatMessageMock).not.toHaveBeenCalled();
    expect(fetchQuotaGuardMock).not.toHaveBeenCalled();
    expect(result.current.draft).toBe('queued mid-run?');
  });

  it('send failure still restores the draft and appends a system bubble (no regression of the original behavior)', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
    postChatMessageMock.mockRejectedValue(new Error('backend unreachable'));
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('this will fail'));
    await act(async () => {
      await result.current.send();
    });

    await waitFor(() => expect(result.current.draft).toBe('this will fail'));
    const messages = useChatStore.getState().messages;
    expect(messages.at(-1)?.role).toBe('system');
    expect(useChatStore.getState().thinking).toBe(false);
  });

  it('reentrant send while the guard query is pending is short-circuited by sending (no duplicate query, no double send)', async () => {
    let release!: (v: { action: 'allow' }) => void;
    fetchQuotaGuardMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        })
    );
    postChatMessageMock.mockResolvedValue(1);
    const { result } = renderHook(() => useChatSend());

    act(() => result.current.setDraft('send only one'));
    let first!: Promise<void>;
    act(() => {
      first = result.current.send();
    });
    // while the guard is pending, sending is already set: reentry is short-circuited at the entry
    expect(result.current.sending).toBe(true);
    await act(async () => {
      await result.current.send();
    });
    expect(fetchQuotaGuardMock).toHaveBeenCalledTimes(1);

    release({ action: 'allow' });
    await act(async () => {
      await first;
    });
    expect(postChatMessageMock).toHaveBeenCalledTimes(1);
    expect(result.current.sending).toBe(false);
    expect(useChatStore.getState().messages).toEqual([
      { seq: 1, role: 'user', content: 'send only one' },
    ]);
  });
});
