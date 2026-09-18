/**
 * @file chatTrajectoryView
 * @description Trajectory view unit tests: turn cards render in execution
 * order with rails and cost stats, step rows expand to call details, and
 * the chat page switches between conversation and trajectory panes.
 */

import { fireEvent, render, screen } from '@testing-library/react';
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
import { TrajectoryView } from '@/widgets/chat/TrajectoryView';
import { LiveTurnTrace } from '@/widgets/chat/TurnTrace';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function backend(_domain: string, name: string) {
  switch (name) {
    case 'list_providers':
      return Promise.resolve([{ id: 'p1', enabled: true, has_api_key: true }]);
    case 'list_subagents':
      return Promise.resolve({ running: [] });
    case 'todo_read':
      return Promise.resolve({ items: [], done: 0, total: 0 });
    default:
      return Promise.resolve({});
  }
}

const TRAIL_STEPS = [
  {
    seq: 2,
    kind: 'llm',
    name: 'round-1',
    summary: 'thinking',
    subagent: 'chat',
    round: 1,
    ms: 1200,
    inputTokens: 33600,
    outputTokens: 1100,
    ttftMs: 350,
    text: '完整的思考内容:先读文件,再判断格式,最后落笔。',
  },
  {
    seq: 3,
    kind: 'tool',
    name: 'read_file',
    summary: 'ok',
    subagent: 'chat',
    toolCallId: 'c-1',
    args: '{"path":"a.txt"}',
    ok: true,
    ms: 12,
    title: 'read_file',
  },
];

function reset(state: Record<string, unknown> = {}) {
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
    lastSteps: [],
    streaming: null,
    ...state,
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
  reset();
  callCapabilityMock.mockReset().mockImplementation(backend);
  subscribeMock.mockClear();
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ messages: [], steps: [] }) } as Response)
  );
});

describe('TrajectoryView', () => {
  it('renders stats, timeline and turn-grouped rows with expandable details', () => {
    reset({
      messages: [
        { seq: 1, role: 'user', content: '读这个文件' },
        { seq: 4, role: 'agent', content: 'done' },
      ],
      trails: [{ msgSeq: 4, userText: '读这个文件', steps: TRAIL_STEPS }],
    });
    render(<TrajectoryView />);
    // toolbar stats
    expect(screen.getByText('轮次 1')).toBeTruthy();
    expect(screen.getByText('调用 1')).toBeTruthy();
    // event rows: user prompt, reasoning block, tool row, assistant reply
    expect(screen.getByText('读这个文件')).toBeTruthy();
    expect(screen.getByText(/完整的思考内容/)).toBeTruthy();
    // expand the tool row: arguments and latency become visible
    fireEvent.click(screen.getByText(/读取文件/));
    expect(screen.getByText('{"path":"a.txt"}')).toBeTruthy();
    expect(screen.getByText(/耗时: 12ms/)).toBeTruthy();
  });

  it('shows the empty state without trails or live steps', () => {
    render(<TrajectoryView />);
    expect(screen.getByText(/暂无执行轨迹/)).toBeTruthy();
  });
});

describe('ChatPage tabs', () => {
  it('switches between conversation and trajectory panes', () => {
    reset({
      messages: [
        { seq: 3, role: 'user', content: '读这个文件' },
        { seq: 4, role: 'agent', content: 'done' },
      ],
      trails: [{ msgSeq: 4, userText: '读这个文件', steps: TRAIL_STEPS }],
    });
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    );
    expect(screen.getByText('done')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: '轨迹' }));
    expect(screen.getByText('读这个文件')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: '对话' }));
    expect(screen.getByText('done')).toBeTruthy();
  });
});

describe('live trace detail', () => {
  it('expands a tool row to the call fact sheet', () => {
    reset({ steps: TRAIL_STEPS, lastSteps: [] });
    render(<LiveTurnTrace />);
    fireEvent.click(screen.getByText('读取文件'));
    expect(screen.getByText('{"path":"a.txt"}')).toBeTruthy();
  });

  it('renders the round lead-in text and meta directly (no step numbers)', () => {
    reset({ steps: TRAIL_STEPS, lastSteps: [] });
    render(<LiveTurnTrace />);
    expect(screen.queryByText('轮 1')).toBeNull(); // round chrome removed
    // thinking is a folding row now: click to reveal the verbatim reasoning
    fireEvent.click(screen.getByText('输出'));
    expect(screen.getByText(/完整的思考内容/)).toBeTruthy();
    expect(screen.queryByText(/首 token 350ms/)).toBeNull(); // meta chrome removed
    expect(screen.queryByText(/第 \d+ 步/)).toBeNull();
  });

  it('mounts during the pre-step phase (thinking, no steps yet)', () => {
    // The first round's llm step only lands at round completion; the trace
    // bar must already be visible while that round streams.
    reset({ thinking: true, steps: [] });
    render(<LiveTurnTrace />);
    expect(screen.getByText('思考中')).toBeTruthy();
    expect(screen.getByText('执行中')).toBeTruthy();
    // No steps yet: the collapsible body stays hidden even though auto-open
    expect(screen.queryByText('轮 1')).toBeNull();
  });

  it('stays hidden once the turn ends (not thinking, no steps)', () => {
    reset({ thinking: false, steps: [] });
    const { container } = render(<LiveTurnTrace />);
    expect(container.querySelector('.chat-trace--live')).toBeNull();
  });
});
