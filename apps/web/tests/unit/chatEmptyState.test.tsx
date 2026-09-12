/**
 * @file chatEmptyState
 * @description Empty-state unit tests when no usable LLM key exists
 * (phase-12 §9.18): with no usable provider confirmed, the Chat page /
 * floating window show the empty state and disable sending (button + Enter);
 * a list_providers query failure does not lock the conversation.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, subscribeMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  subscribeMock: vi.fn(() => () => {}),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/bridge/stream', () => ({ subscribe: subscribeMock }));

import { ChatPage } from '@/pages/chat/ChatPage';
import { FloatingChat } from '@/widgets/FloatingChat';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

/** list_providers return value (rewritten between cases); PROVIDERS_FAIL=true simulates a query failure */
let PROVIDERS: Array<Record<string, unknown>> = [];
let PROVIDERS_FAIL = false;

function backend(_domain: string, name: string) {
  switch (name) {
    case 'list_providers':
      return PROVIDERS_FAIL
        ? Promise.reject(new Error('network down'))
        : Promise.resolve(PROVIDERS);
    case 'get_setting':
      return Promise.resolve({ value: 'queue' });
    case 'list_subagents':
      return Promise.resolve({ running: [] });
    default:
      return Promise.resolve({});
  }
}

beforeAll(() => {
  // Page copy moved to the chat ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
  initI18n();
  // jsdom gap: MessageList's scroll effect needs matchMedia / scrollIntoView
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  PROVIDERS = [];
  PROVIDERS_FAIL = false;
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
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
});

/** Type into the Chat page input (the placeholder changes with the empty state; wait for it to settle first) */
async function typeIntoChatPage(text: string) {
  const box = screen.getByPlaceholderText(/说点什么|先在设置里配置 LLM/);
  fireEvent.change(box, { target: { value: text } });
  return screen.getByRole('button', { name: '发送' });
}

describe('ChatPage empty state without keys', () => {
  it('no available providers: empty state shown, placeholder changes, send stays disabled after typing', async () => {
    PROVIDERS = [{ id: 'p1', enabled: true, has_api_key: false }];
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    expect(await screen.findByText(/还没有可用的 LLM 提供商/)).toBeTruthy();
    expect(screen.getByRole('link', { name: '设置 → LLM' })).toBeTruthy();

    const send = await typeIntoChatPage('你好');
    expect(send).toBeDisabled(); // send stays disabled even with a draft (Enter also exits early through send())
    expect(screen.getByPlaceholderText('先在设置里配置 LLM')).toBeTruthy();
  });

  it('available providers: no empty state and sending works after typing', async () => {
    PROVIDERS = [{ id: 'p1', enabled: true, has_api_key: true }];
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_providers'));
    const send = await typeIntoChatPage('你好');
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(screen.queryByText(/还没有可用的 LLM 提供商/)).toBeNull();
  });

  it('list_providers failure: not misread as keyless and sending is not locked', async () => {
    PROVIDERS_FAIL = true;
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    await waitFor(() => expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_providers'));
    const send = await typeIntoChatPage('你好');
    await waitFor(() => expect(send).not.toBeDisabled());
    expect(screen.queryByText(/还没有可用的 LLM 提供商/)).toBeNull();
  });
});

describe('FloatingChat empty state without keys', () => {
  it('shows the empty state and disables send after expanding the panel', async () => {
    PROVIDERS = [{ id: 'p1', enabled: false, has_api_key: true }]; // disabled ≠ available
    render(
      <MemoryRouter>
        <FloatingChat />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /打开对话/ }));
    expect(await screen.findByText(/还没有可用的 LLM 提供商/)).toBeTruthy();
    const box = screen.getByPlaceholderText('先在设置里配置 LLM');
    fireEvent.change(box, { target: { value: '你好' } });
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();
  });
});
