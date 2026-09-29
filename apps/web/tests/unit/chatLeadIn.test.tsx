/**
 * @file chatLeadIn
 * @description Conversational multi-round delivery: the closing message joins
 * the visible lead-in texts with the final answer, and the closed trace must
 * not render a carried round text a second time (containment dup, not
 * equality).
 */

import { fireEvent, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: vi.fn().mockResolvedValue({}),
}));

import { MessageList } from '@/widgets/chat/MessageList';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

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
    prevTurnSteps: [],
    streaming: null,
  });
});

function renderWith() {
  return render(
    <MemoryRouter>
      <MessageList />
    </MemoryRouter>
  );
}

describe('lead-in delivery vs the closed trace', () => {
  it('a round text carried by the closing message renders once, not twice', () => {
    const lead = '我是 Lucien,这个工作台的常驻协调人。';
    const full = `${lead}\n\n查完了,实证在这:今天 11 次调用全是 MiniMax。`;
    useChatStore.setState({
      messages: [{ seq: 4, role: 'agent', content: full, ts: 1004 }],
      trails: [
        {
          msgSeq: 4,
          userText: '你是谁?是什么模型?',
          steps: [
            {
              seq: 2,
              kind: 'llm',
              name: 'round-1',
              summary: lead.slice(0, 12),
              ts: 1002,
              round: 1,
              text: lead,
            },
          ],
        },
      ],
    });
    const { container } = renderWith();
    // Expand the closed trace: the round row would duplicate the lead-in the
    // bubble already carries.
    fireEvent.click(container.querySelector('.chat-trace__head') as Element);
    const occurrences = (container.textContent ?? '').split(lead).length - 1;
    expect(occurrences).toBe(1);
    expect(container.querySelector('.chat-round__out')).toBeNull();
  });

  it('a round text not carried by the closing message still renders in the trace', () => {
    useChatStore.setState({
      messages: [{ seq: 4, role: 'agent', content: '这是最终结论。', ts: 1004 }],
      trails: [
        {
          msgSeq: 4,
          userText: 'hi',
          steps: [
            {
              seq: 2,
              kind: 'llm',
              name: 'round-1',
              summary: '另一段话',
              ts: 1002,
              round: 1,
              text: '另一段话。',
            },
          ],
        },
      ],
    });
    const { container } = renderWith(useChatStore.getState().messages[0]);
    fireEvent.click(container.querySelector('.chat-trace__head') as Element);
    expect(container.querySelector('.chat-round__out')).not.toBeNull();
    expect(container.textContent).toContain('另一段话。');
  });
});
