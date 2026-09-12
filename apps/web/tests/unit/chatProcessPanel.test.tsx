/**
 * @file chatProcessPanel
 * @description Chat redesign (2026-09): the execution timeline (expand while
 * running, auto-collapse on turn end), the composer's send -> stop morph, and
 * the right panel's plan/agents sections.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
import { ProcessTimeline } from '@/widgets/chat/ProcessTimeline';
import { RightPanel } from '@/widgets/chat/RightPanel';
import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

let seq = 1000;
function stepEvent(kind: string, name: string, summary: string, ts: number): ChatEvent {
  seq += 1;
  return { seq, type: 'agent.step', payload: { kind, name, summary, subagent: 'chat' }, ts };
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
    lastSteps: [],
    stepsOpen: false,
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

describe('ProcessTimeline', () => {
  it('stays expanded while the turn runs: think rows and localized tool labels', () => {
    const { dispatch } = useChatStore.getState();
    dispatch(stepEvent('llm', 'round-1', '我先查一下', 100));
    dispatch(stepEvent('tool', 'notes__create_note', 'created', 103));
    render(<ProcessTimeline />);
    expect(screen.getByText('执行过程')).toBeTruthy();
    expect(screen.getByText('思考')).toBeTruthy();
    expect(screen.getByText('创建笔记')).toBeTruthy();
    expect(screen.queryByText('notes__create_note')).toBeNull(); // display layer humanizes
  });

  it('agent.message folds the trajectory into a collapsed one-line summary', () => {
    const { dispatch } = useChatStore.getState();
    dispatch(stepEvent('llm', 'round-1', 'a', 100));
    dispatch(stepEvent('tool', 'notes__create_note', 'b', 103));
    dispatch({ seq: 2000, type: 'agent.message', payload: { content: 'done' } });
    render(<ProcessTimeline />);
    // collapsed: the summary line replaces the step list
    expect(screen.getByText(/已执行 2 步 · 1 次工具/)).toBeTruthy();
    expect(screen.queryByText('创建笔记')).toBeNull();
    // reopening shows the steps again
    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText('创建笔记')).toBeTruthy();
  });

  it('hard stop (clearThinking) also folds the live trajectory', () => {
    const { dispatch } = useChatStore.getState();
    dispatch(stepEvent('tool', 'notes__create_note', 'b', 103));
    useChatStore.setState({ thinking: true });
    useChatStore.getState().clearThinking();
    render(<ProcessTimeline />);
    expect(screen.getByText(/已执行 1 步 · 1 次工具/)).toBeTruthy();
  });

  it('renders nothing without steps', () => {
    const { container } = render(<ProcessTimeline />);
    expect(container.querySelector('.chat-proc')).toBeNull();
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
  it('renders plan todos with status styling and running subagents', async () => {
    listTodosMock.mockResolvedValue({
      items: [
        { content: '查资料', status: 'done' },
        { content: '写笔记', status: 'in_progress' },
      ],
      done: 1,
      total: 2,
    });
    listSubagentsMock.mockResolvedValue({
      running: [{ id: 'r1', name: 'indexer', status: 'running', goal: '建索引', started_ts: 1 }],
    });
    render(
      <MemoryRouter>
        <RightPanel taskCards={null} />
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText('查资料')).toBeTruthy());
    expect(screen.getByText('写笔记')).toBeTruthy();
    expect(screen.getByText('indexer')).toBeTruthy();
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
