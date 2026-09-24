/**
 * @file chatSpeaker
 * @description Group-chat attribution: agent bubbles carry a speaker header
 * (name + character head) when the voice changes; consecutive messages of
 * the same speaker stay clean; notices and system rows never carry one.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: vi.fn().mockResolvedValue({}),
}));

import { MessageList } from '@/widgets/chat/MessageList';
import { type ChatEvent, type ChatMessage, useChatStore } from '@/stores/chatStore';
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
    lastSteps: [],
    roundTexts: [],
    streaming: null,
  });
}

let seq = 500;
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
  seq = 500;
});

function renderStream() {
  return render(
    <MemoryRouter>
      <MessageList />
    </MemoryRouter>
  );
}

describe('group-chat speaker attribution (MessageList)', () => {
  it('renders a name header when the voice changes, once per speaker run', () => {
    resetStore([
      msg('user', '帮我分析'),
      msg('agent', '收到，这就派 Elio。'), // host, no speaker field (pre-team shape)
      msg('agent', '讲解如下……', { speaker: 'explainer' }),
      msg('agent', '补充一点。', { speaker: 'explainer' }), // same voice: no header
    ]);
    const { container } = renderStream();
    const headers = container.querySelectorAll('.chat-speaker__name');
    expect(Array.from(headers).map((h) => h.textContent)).toEqual(['Lucien', 'Elio']);
    // the character head rides the first header of each run
    expect(container.querySelectorAll('.chat-speaker__avatar').length).toBe(2);
    expect(screen.getByText('讲解如下……')).toBeTruthy();
  });

  it('switching back to the host opens a new header run', () => {
    resetStore([
      msg('agent', 'host line', { speaker: 'explainer' }),
      msg('user', '谢谢'),
      msg('agent', 'host again'),
    ]);
    const { container } = renderStream();
    const headers = container.querySelectorAll('.chat-speaker__name');
    expect(Array.from(headers).map((h) => h.textContent)).toEqual(['Elio', 'Lucien']);
  });

  it('notices and system rows never carry a speaker header', () => {
    resetStore([
      msg('agent', '[done] explainer: 任务完成', { kind: 'notice' }),
      msg('system', '会话已切换'),
      msg('agent', 'normal answer'),
    ]);
    const { container } = renderStream();
    expect(container.querySelectorAll('.chat-speaker').length).toBe(1);
    expect(container.querySelectorAll('.chat-speaker__name')[0].textContent).toBe('Lucien');
  });

  it('the live trace header names the thinking member', () => {
    resetStore([]);
    const ev: ChatEvent = {
      seq: 900,
      type: 'agent.delta',
      payload: { round: 1, text: '', subagent: 'Elio' },
      ts: 1999,
    };
    useChatStore.setState({ thinking: true, streaming: { text: '', round: 1, subagent: 'Elio' } });
    renderStream();
    useChatStore.getState().dispatch(ev);
    expect(screen.getByText('Elio 正在思考…')).toBeTruthy();
  });
});
