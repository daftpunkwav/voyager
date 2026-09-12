/**
 * @file chatSend
 * @description sendUserTurn: pushes one user message into the main timeline
 * from any page (phase-17); phase-67 adds the pre-send quota guard: a full
 * quota rejects without POST, ≥80% warns but still sends.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { setOpen, fetchQuotaGuardMock } = vi.hoisted(() => ({
  setOpen: vi.fn(),
  fetchQuotaGuardMock: vi.fn(),
}));

vi.mock('@/stores/floatingStore', () => ({
  useFloatingStore: {
    getState: () => ({ setOpen }),
  },
}));

vi.mock('@/bridge/quotaGuard', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/quotaGuard')>()),
  fetchQuotaGuard: fetchQuotaGuardMock,
}));

import {
  postChatMessage,
  fetchChatHistory,
  fetchChatHistoryBefore,
  sendUserTurn,
} from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

beforeAll(() => {
  // bridge copy moved to the chat ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
  initI18n();
});

describe('sendUserTurn', () => {
  beforeEach(() => {
    setOpen.mockReset();
    fetchQuotaGuardMock.mockReset();
    // Allow by default: cases that do not stub quota results explicitly are unaffected by the guard
    fetchQuotaGuardMock.mockResolvedValue({ action: 'allow' });
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ seq: 42 })));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('writes to chatStore and opens the floating window after a successful POST', async () => {
    await sendUserTurn('  [graph] node=abc. user=why linked  ');
    expect(fetch).toHaveBeenCalledWith(
      '/api/chat/messages',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      })
    );
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      content: '[graph] node=abc. user=why linked',
      session: '',
    });
    expect(useChatStore.getState().messages).toEqual([
      {
        seq: 42,
        role: 'user',
        content: '[graph] node=abc. user=why linked',
      },
    ]);
    expect(setOpen).toHaveBeenCalledWith(true);
  });

  it('does not write the message or open the floating window when the backend fails', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(null, 500));
    await expect(sendUserTurn('analyze this repo')).rejects.toThrow('发送失败(500)');
    expect(useChatStore.getState().messages).toEqual([]);
    expect(setOpen).not.toHaveBeenCalled();
  });

  it('quota block: throws without POST, without writing messages, without opening the floating window', async () => {
    fetchQuotaGuardMock.mockResolvedValue({
      action: 'block',
      reason: '今日 token 配额已用完，可在设置中调高或明日再试',
    });
    await expect(sendUserTurn('analyze this repo')).rejects.toThrow('今日 token 配额已用完');
    expect(fetch).not.toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual([]);
    expect(setOpen).not.toHaveBeenCalled();
  });

  it('≥80% warn: still sends after the warning', async () => {
    fetchQuotaGuardMock.mockResolvedValue({ action: 'warn', ratio: 0.8 });
    await sendUserTurn('continue analysis');
    expect(fetch).toHaveBeenCalled();
    expect(useChatStore.getState().messages).toEqual([
      { seq: 42, role: 'user', content: 'continue analysis' },
    ]);
    expect(setOpen).toHaveBeenCalledWith(true);
    const toasts = useUIStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0].type).toBe('warning');
    expect(toasts[0].message).toContain('80%');
  });
});

describe('postChatMessage: seq and error envelope', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('seq=0 is a valid first message: resolves to 0 (truthiness checks would misread it as failure)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ seq: 0 })));
    await expect(postChatMessage('hello')).resolves.toBe(0);
  });

  it('failure with an error envelope: code/message surface instead of an uninformative status code', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { error: { code: 'RATE_LIMITED', message: 'rate limited, retry later', hint: '' } },
            429
          )
        )
    );
    const err = await postChatMessage('hello').then(
      () => null,
      (e) => e
    );
    expect(err).toBeInstanceOf(Error);
    expect(err.code).toBe('RATE_LIMITED');
    expect(err.message).toBe('rate limited, retry later');
  });

  it('failure without a JSON envelope: falls back to the status-code copy (same as the old behavior)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(null, 502)));
    await expect(postChatMessage('hello')).rejects.toThrow('发送失败(502)');
  });
});

describe('fetchChatHistory / fetchChatHistoryBefore', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('throws explicitly on 500 instead of silently returning empty history', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(null, 500)));
    await expect(fetchChatHistory()).rejects.toThrow('聊天历史加载失败(500)');
  });

  it('newest page: requests the default window and unwraps messages + has_more', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        has_more: true,
        messages: [{ seq: 1, type: 'user.message', payload: { content: 'a' } }],
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchChatHistory()).resolves.toEqual({
      hasMore: true,
      messages: [{ seq: 1, type: 'user.message', payload: { content: 'a' } }],
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/messages?limit=200', expect.anything());
  });

  it('older page: passes the before_seq cursor through', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ has_more: false, messages: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchChatHistoryBefore(7, 50)).resolves.toEqual({
      hasMore: false,
      messages: [],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/messages?before_seq=7&limit=50',
      expect.anything()
    );
  });
});
