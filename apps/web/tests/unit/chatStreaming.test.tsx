/**
 * @file chatStreaming
 * @description Streaming typing (baseline 2026-09) unit tests: agent.delta
 * accumulates, a round change restarts, agent.message finalizes and clears
 * the slot; bubble rendering lives in MessageList.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { MessageList } from '@/widgets/chat/MessageList';
import { useChatStore, type ChatEvent } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
}

beforeAll(() => {
  // Component copy moved to the chat ns: initialize explicitly (default zh-CN)
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
  seq = 0;
  useChatStore.setState({
    messages: [],
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    thinking: true,
    connected: true,
    currentStep: null,
    streaming: null,
  });
});

describe('chatStore streaming', () => {
  it('accumulates deltas within the same round', () => {
    dispatch('agent.delta', { round: 1, text: '你好', subagent: 'chat' });
    dispatch('agent.delta', { round: 1, text: '世界', subagent: 'chat' });
    expect(useChatStore.getState().streaming?.text).toBe('你好世界');
  });

  it('a round change restarts: intermediate-round lead-in does not leak into the final round', () => {
    dispatch('agent.delta', { round: 1, text: '我先查一下', subagent: 'chat' });
    dispatch('agent.delta', { round: 2, text: '答案是', subagent: 'chat' });
    const s = useChatStore.getState().streaming;
    expect(s?.round).toBe(2);
    expect(s?.text).toBe('答案是');
  });

  it('agent.message finalizes the message and clears the typing slot', () => {
    dispatch('agent.delta', { round: 1, text: '生成中', subagent: 'chat' });
    dispatch('agent.message', { content: '正式回复' });
    const st = useChatStore.getState();
    expect(st.streaming).toBeNull();
    expect(st.thinking).toBe(false);
    expect(st.messages.at(-1)?.content).toBe('正式回复');
  });

  it('a delta with empty text produces no typing slot content (empty string renders nothing)', () => {
    dispatch('agent.delta', { round: 1, text: '', subagent: 'chat' });
    expect(useChatStore.getState().streaming?.text).toBe('');
  });
});

describe('MessageList streaming', () => {
  it('streams the round text inside the live trace round block; the final message is the only bubble', () => {
    const { container } = render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    // No standalone typing bubble: streaming text lives inside the trace.
    expect(container.querySelector('.chat-caret')).toBeNull();
    act(() => {
      dispatch('agent.delta', { round: 1, text: '打字中', subagent: 'chat' });
    });
    // The live round folding row carries the streaming text (collapsed until clicked).
    expect(screen.getAllByText(/正在输出/).length).toBeGreaterThanOrEqual(1);
    expect(container.querySelector('.chat-bubble--agent .chat-caret')).toBeNull();
    const foldHead = [...container.querySelectorAll('.chat-fold__head')].at(-1) as Element;
    fireEvent.click(foldHead);
    expect(container.querySelector('.chat-fold__body')?.textContent).toContain('打字中');
    act(() => {
      dispatch('agent.message', { content: '正式回复' });
    });
    // The trace folds (live steps cleared) and the closing message renders.
    expect(screen.getByText('正式回复')).toBeTruthy();
    expect(container.querySelector('.chat-round__text')?.textContent ?? '').not.toContain('打字中');
  });
});
