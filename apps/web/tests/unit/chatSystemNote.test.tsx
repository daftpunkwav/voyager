/**
 * @file chatSystemNote
 * @description Harness-voice rendering: wind-down caps ([中断]/[预算], kind
 * warning) and degraded provider text (kind error) render as system note
 * cards — tinted, icon, no speaker header, no agent bubble — so they can
 * never be mistaken for a Lucien answer; plain answers keep the bubble.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: vi.fn().mockResolvedValue({}),
}));

import { MessageList } from '@/widgets/chat/MessageList';
import { type ChatMessage, useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function resetStore(messages: ChatMessage[]) {
  useChatStore.setState({
    messages,
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
    steps: [],
    trails: [],
    prevTurnSteps: [],
    roundTexts: [],
    streaming: null,
  });
}

let seq = 700;
function msg(
  role: ChatMessage['role'],
  content: string,
  extra: Partial<ChatMessage> = {}
): ChatMessage {
  seq += 1;
  return { seq, role, content, ts: 1000 + seq, ...extra };
}

beforeAll(() => {
  initI18n();
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
  seq = 700;
});

function renderStream() {
  return render(
    <MemoryRouter>
      <MessageList />
    </MemoryRouter>
  );
}

describe('harness voice renders as system notes (MessageList)', () => {
  it('wind-down text (warning) renders the system card, not an agent bubble', () => {
    resetStore([
      msg('agent', '[中断] 已达 ReAct 轮数上限(50);可在设置提高 agent.rounds.max', {
        kind: 'warning',
      }),
    ]);
    const { container } = renderStream();
    const note = container.querySelector('.chat-sysnote--warning');
    expect(note).not.toBeNull();
    expect(note?.getAttribute('role')).toBe('status');
    expect(note?.textContent).toContain('ReAct 轮数上限');
    expect(container.querySelector('.chat-bubble--agent')).toBeNull();
    expect(container.querySelector('.chat-speaker')).toBeNull();
  });

  it('degraded provider text (error) renders the error card with alert semantics', () => {
    resetStore([msg('agent', '(LLM call failed: HTTP 529)', { kind: 'error' })]);
    const { container } = renderStream();
    const note = container.querySelector('.chat-sysnote--error');
    expect(note).not.toBeNull();
    expect(note?.getAttribute('role')).toBe('alert');
    expect(container.querySelector('.chat-bubble--agent')).toBeNull();
  });

  it('plain answers keep the agent bubble (no note chrome)', () => {
    resetStore([msg('agent', '你好。刚才那句 ok 被服务集群的 529 负载错误吞了。')]);
    const { container } = renderStream();
    expect(container.querySelector('.chat-bubble--agent')).not.toBeNull();
    expect(container.querySelector('.chat-sysnote')).toBeNull();
    expect(screen.getByText(/529 负载错误吞了/)).toBeTruthy();
  });
});
