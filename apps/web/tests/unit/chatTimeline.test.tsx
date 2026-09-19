/**
 * @file chatTimeline
 * @description Conversation timeline integration (the 2026-09 inline-trace
 * redesign): the live turn's trace stays expanded while tool steps stream in
 * and streaming text flows inside its round block; closed turns render their
 * collapsed trail above the answer; note receipts re-parent below the reply
 * that produced them; the composer's send -> stop morph; the right panel's
 * plan / agents / deliverables sections.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, listTodosMock, listSubagentsMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  listTodosMock: vi.fn(),
  listSubagentsMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/agent', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/agent')>()),
  listTodos: listTodosMock,
  listSubagents: listSubagentsMock,
}));

import { ChatComposer } from '@/widgets/chat/ChatComposer';
import { MessageList } from '@/widgets/chat/MessageList';
import { RightPanel } from '@/widgets/chat/RightPanel';
import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

let seq = 1000;
function stepEvent(
  kind: string,
  name: string,
  summary: string,
  ts: number,
  detail: Record<string, unknown> = {}
): ChatEvent {
  seq += 1;
  return {
    seq,
    type: 'agent.step',
    payload: { kind, name, summary, subagent: 'chat', detail },
    ts,
  };
}

function resetStore() {
  seq = 1000;
  useChatStore.setState({
    messages: [],
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
  resetStore();
  callCapabilityMock.mockReset().mockResolvedValue({});
  listTodosMock.mockReset().mockResolvedValue({ items: [], done: 0, total: 0 });
  listSubagentsMock.mockReset().mockResolvedValue({ running: [] });
});

function renderStream() {
  return render(
    <MemoryRouter>
      <MessageList />
    </MemoryRouter>
  );
}

describe('inline live trace (MessageList)', () => {
  it('stays expanded while the turn runs: round block, tool rows, localized labels', () => {
    const { dispatch } = useChatStore.getState();
    useChatStore.setState({ thinking: true });
    dispatch(stepEvent('llm', 'round-1', '我先查一下', 100, { round: 1 }));
    dispatch(stepEvent('tool', 'notes__create_note', 'created', 103));
    const { container } = renderStream();
    expect(container.querySelector('.chat-trace--live')).not.toBeNull();
    // round blocks have no chrome (no round numbers): only foldable rows
    expect(screen.queryByText('轮 1')).toBeNull();
    expect(screen.getByText('创建笔记')).toBeTruthy();
    expect(screen.queryByText('notes__create_note')).toBeNull(); // display layer humanizes
    // the group header summarizes the turn
    expect(screen.getByText(/思考 1 次/)).toBeTruthy();
    expect(screen.getByText(/工具 1 次/)).toBeTruthy();
  });

  it('streams the round text inside the trace; the whole unit collapses only manually', () => {
    const { dispatch } = useChatStore.getState();
    useChatStore.setState({ thinking: true });
    dispatch(stepEvent('llm', 'round-1', 'a', 100));
    dispatch(stepEvent('tool', 'notes__create_note', 'b', 103));
    const { container } = renderStream();
    act(() => {
      dispatch({
        seq: 2000,
        type: 'agent.delta',
        payload: { round: 1, text: '答案是', subagent: 'chat' },
      });
    });
    // The trace stays open: streaming text renders inside the round block's
    // folding row (no standalone typing bubble), tool rows stay visible.
    expect(screen.getByText('创建笔记')).toBeTruthy();
    expect(screen.getAllByText(/正在输出/).length).toBeGreaterThanOrEqual(1);
    // the caret rides the live round output row (no standalone bubble)
    expect(container.querySelector('.chat-round__out .chat-caret')).not.toBeNull();
    // manual collapse hides the rows; the header brings them back
    fireEvent.click(screen.getByText(/工具 1 次/));
    expect(screen.queryByText('创建笔记')).toBeNull();
    fireEvent.click(screen.getByText(/工具 1 次/));
    expect(screen.getByText('创建笔记')).toBeTruthy();
  });

  it('agent.message folds the closed trail above the answer; collapsed by default', () => {
    const { dispatch } = useChatStore.getState();
    useChatStore.setState({ thinking: true });
    dispatch(stepEvent('llm', 'round-1', 'a', 100));
    dispatch(stepEvent('tool', 'notes__create_note', 'b', 103));
    dispatch({ seq: 2000, type: 'agent.message', payload: { content: 'done' } });
    const { container } = renderStream();
    expect(screen.getByText('done')).toBeTruthy();
    expect(container.querySelector('.chat-trace--live')).toBeNull();
    // collapsed: the one-line summary replaces the step list
    expect(screen.getByText(/已执行 2 步 · 1 次工具/)).toBeTruthy();
    expect(screen.queryByText('创建笔记')).toBeNull();
    // reopening shows the steps again
    fireEvent.click(screen.getByText(/已执行 2 步/));
    expect(screen.getByText('创建笔记')).toBeTruthy();
  });

  it('renders no trace without steps', () => {
    const { container } = renderStream();
    expect(container.querySelector('.chat-trace')).toBeNull();
  });

  it('keeps note receipts attached to their turn instead of the stream tail', () => {
    // Turn 1 closed (answer seq 2), then a second user question arrived; the
    // note receipt (seq 2, same event-log order) must sit between the two
    // turns, not stack after the newest message.
    useChatStore.setState({
      messages: [
        { seq: 1, role: 'user', content: '第一问' },
        { seq: 2, role: 'agent', content: '第一答' },
        { seq: 3, role: 'user', content: '第二问' },
      ],
      artifacts: [{ seq: 2, noteId: 'n1', title: '周报' }],
    });
    const { container } = renderStream();
    const card = container.querySelector('.note-artifact');
    const secondAsk = [...container.querySelectorAll('.chat-bubble--user')].at(-1);
    expect(card).not.toBeNull();
    expect(secondAsk).not.toBeNull();
    // card precedes the second user bubble in document order
    const cardEl = card as Element;
    const askEl = secondAsk as Element;
    expect(cardEl.compareDocumentPosition(askEl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // re-parented under the answer it belongs to: after the first agent
    // bubble, before the second user bubble
    const firstAnswer = [...container.querySelectorAll('.chat-bubble--agent')].at(-1) as Element;
    expect(
      firstAnswer.compareDocumentPosition(cardEl) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('re-parents a mid-turn receipt below the reply that produced it', () => {
    // Real event-log order: the receipt (seq 2) lands while the tools run,
    // strictly BEFORE the closing reply (seq 3). The card must still end up
    // below that reply, not between the user message and it.
    useChatStore.setState({
      messages: [
        { seq: 1, role: 'user', content: '第一问' },
        { seq: 3, role: 'agent', content: '第一答' },
        { seq: 4, role: 'user', content: '第二问' },
      ],
      artifacts: [{ seq: 2, noteId: 'n1', title: '周报' }],
    });
    const { container } = renderStream();
    const cardEl = container.querySelector('.note-artifact') as Element;
    const firstAnswer = container.querySelector('.chat-bubble--agent') as Element;
    const secondAsk = [...container.querySelectorAll('.chat-bubble--user')].at(-1) as Element;
    expect(
      firstAnswer.compareDocumentPosition(cardEl) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      cardEl.compareDocumentPosition(secondAsk) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('keeps multiple receipts of one turn in creation order below the reply', () => {
    useChatStore.setState({
      messages: [
        { seq: 1, role: 'user', content: '第一问' },
        { seq: 4, role: 'agent', content: '第一答' },
      ],
      artifacts: [
        { seq: 2, noteId: 'n1', title: '笔记一' },
        { seq: 3, noteId: 'n2', title: '笔记二' },
      ],
    });
    const { container } = renderStream();
    const cards = [...container.querySelectorAll('.note-artifact')];
    expect(cards).toHaveLength(2);
    const answer = container.querySelector('.chat-bubble--agent') as Element;
    // both sit below the reply, first note above second note
    for (const card of cards) {
      expect(answer.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(
      cards[0].compareDocumentPosition(cards[1]) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(cards[0].textContent).toContain('笔记一');
  });
});

describe('ChatComposer send -> stop morph', () => {
  const composerStub = {
    draft: '',
    setDraft: vi.fn(),
    sending: false,
    llmMissing: false,
    send: vi.fn(),
  };

  it('idle: shows the send button', () => {
    render(<ChatComposer composer={composerStub} placeholder="" className="chat-input" />);
    expect(screen.getByRole('button', { name: '发送' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: '停止' })).toBeNull();
  });

  it('running: the button becomes 停止 and clicking it interrupts the chat turn', () => {
    const onStop = vi.fn();
    render(
      <ChatComposer
        composer={composerStub}
        placeholder=""
        className="chat-input"
        running
        onStop={onStop}
      />
    );
    const stop = screen.getByRole('button', { name: '停止' });
    expect(stop.className).toContain('btn-danger'); // danger styling, per AGENTS.md
    fireEvent.click(stop);
    expect(onStop).toHaveBeenCalledTimes(1);
  });
});

describe('RightPanel', () => {
  it('renders plan todos with status styling and running subagents with elapsed time', async () => {
    listTodosMock.mockResolvedValue({
      items: [
        { content: '查资料', status: 'done' },
        { content: '写笔记', status: 'in_progress' },
      ],
      done: 1,
      total: 2,
    });
    listSubagentsMock.mockResolvedValue({
      running: [
        {
          id: 'r1',
          name: 'indexer',
          status: 'running',
          goal: '建索引',
          started_ts: Date.now() / 1000 - 65,
        },
      ],
    });
    render(
      <MemoryRouter>
        <RightPanel taskCards={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('查资料')).toBeTruthy());
    expect(screen.getByText('写笔记')).toBeTruthy();
    expect(screen.getByText('indexer')).toBeTruthy();
    expect(screen.getByText('1/2')).toBeTruthy(); // plan counter
    expect(screen.getByText(/1 分/)).toBeTruthy(); // elapsed runtime
    expect(screen.queryByText(/暂无计划/)).toBeNull();
    expect(screen.queryByText(/没有正在运行/)).toBeNull();
  });

  it('shows empty states when nothing is planned or running', async () => {
    render(
      <MemoryRouter>
        <RightPanel taskCards={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/暂无计划/)).toBeTruthy());
    expect(screen.getByText(/没有正在运行/)).toBeTruthy();
  });

  it('clicking a running agent interrupts that instance', async () => {
    listSubagentsMock.mockResolvedValue({
      running: [{ id: 'r9', name: 'indexer', status: 'running', goal: '建索引', started_ts: 1 }],
    });
    render(
      <MemoryRouter>
        <RightPanel taskCards={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('indexer')).toBeTruthy());
    fireEvent.click(screen.getByText('indexer'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', { id_or_name: 'r9' })
    );
  });
});
