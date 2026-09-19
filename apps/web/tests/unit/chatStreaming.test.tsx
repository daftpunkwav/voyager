/**
 * @file chatStreaming
 * @description Streaming typing (baseline 2026-09) unit tests: agent.delta
 * accumulates, a round change restarts, agent.message finalizes and clears
 * the slot; bubble rendering lives in MessageList.
 */

import { act, render, screen } from '@testing-library/react';
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
    steps: [],
    trails: [],
    lastSteps: [],
    roundTexts: [],
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
    // The live round output row carries the streaming text, caret included.
    expect(container.querySelector('.chat-round__out')?.textContent).toContain('打字中');
    expect(container.querySelector('.chat-round__out .chat-caret')).not.toBeNull();
    act(() => {
      dispatch('agent.message', { content: '正式回复' });
    });
    // The trace folds (live steps cleared) and the closing message renders:
    // the closing message is the only rendered output.
    expect(screen.getByText('正式回复')).toBeTruthy();
    expect(container.querySelector('.chat-round__out')).toBeNull();
  });

  it('a system op emitted before the first round marker renders inside that round block', () => {
    // Backend compaction runs at the round boundary: the compact step lands
    // BEFORE round 1's llm marker and must not be dropped from the trace.
    dispatch('agent.step', { kind: 'system', name: 'compact', summary: '压缩上下文' });
    dispatch('agent.step', {
      kind: 'llm',
      name: 'round-1',
      summary: 't',
      detail: { round: 1 },
    });
    const { container } = render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    const opRow = container.querySelector('.chat-trace__rowbtn--op');
    expect(opRow).not.toBeNull();
    expect(opRow?.textContent).toContain('压缩上下文');
  });
});

describe('MessageList interrupted turn trace', () => {
  it('keeps the interrupted turn trace visible after the stop receipt (system bubble)', () => {
    useChatStore.getState().appendLocal({ seq: 1, role: 'user', content: '读文件' });
    dispatch('agent.step', { kind: 'tool', name: 'notes__read', summary: 'r', subagent: 'chat' });
    act(() => {
      // The stop flow folds the live steps into an interrupted trail, then the
      // stop receipt lands as a system bubble right after clearThinking.
      useChatStore.getState().clearThinking();
      useChatStore.getState().addSystem('已停止');
    });
    const { container } = render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    // The live trace is gone; the interrupted turn's closed trace remains.
    expect(container.querySelector('.chat-trace--live')).toBeNull();
    expect(container.querySelector('.chat-trace:not(.chat-trace--live)')).not.toBeNull();
  });

  it('interrupted trace still shows when an earlier completed turn exists (trails ascend by msgSeq)', () => {
    // Turn 1 completes normally: its trail closes under the reply's seq.
    useChatStore.getState().appendLocal({ seq: 1, role: 'user', content: '第一问' });
    dispatch('agent.step', { kind: 'tool', name: 'notes__read', summary: 'r', subagent: 'chat' });
    dispatch('agent.message', { content: '答一' });
    // Turn 2 is interrupted; the negative-keyed trail sorts BEFORE turn 1's.
    useChatStore.getState().appendLocal({ seq: 4, role: 'user', content: '第二问' });
    dispatch('agent.step', { kind: 'tool', name: 'notes__read', summary: 'r2', subagent: 'chat' });
    act(() => {
      useChatStore.getState().clearThinking();
      useChatStore.getState().addSystem('已停止');
    });
    const { container } = render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    // Turn 1's closed trace above its answer + the interrupted turn's trace at the tail.
    expect(container.querySelectorAll('.chat-trace:not(.chat-trace--live)')).toHaveLength(2);
  });
});
