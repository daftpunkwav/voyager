/**
 * @file chatTasks
 * @description Phase-05 unit tests: task card completeness (completed/failed
 * build cards even without a prior progress, label priority, jump links) and
 * note artifact inline preview (expand fetches the full text / failure
 * explanation / collapse).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, beforeAll, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ServiceError } from '@/bridge/client';
import { MessageList } from '@/widgets/chat/MessageList';
import { TaskCards } from '@/widgets/chat/TaskCards';
import { useChatStore, type ChatEvent, type ProgressCard } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

let seq = 0;
function dispatch(type: string, payload: Record<string, unknown>) {
  seq += 1;
  useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
}

function card(partial: Partial<ProgressCard> & { key: string }): ProgressCard {
  return { label: partial.key, progress: 0, stage: '', status: 'running', ...partial };
}

beforeAll(() => {
  // Component copy moved to the chat ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
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
    thinking: false,
    connected: true,
    currentStep: null,
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
});

describe('chatStore task card completeness', () => {
  it('a bare task.completed (no prior progress) still builds a completed card', () => {
    dispatch('task.completed', { job_id: 'j-1', project: 'demo', progress: 1.0 });
    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toContain('j-1');
    expect(cards['j-1']).toMatchObject({
      label: 'demo',
      status: 'completed',
      progress: 1,
    });
  });

  it('a bare task.failed (no prior progress) still builds a failed card with the error visible', () => {
    dispatch('task.failed', { job_id: 'j-2', project: 'demo', error: '队列爆炸' });
    expect(useChatStore.getState().cards['j-2']).toMatchObject({
      status: 'failed',
      error: '队列爆炸',
    });
  });

  it('sources-style payloads (no project) label the card with kind instead of the bare uuid', () => {
    dispatch('task.failed', { source_id: 'abc-123', kind: 'doc', error: '解析失败: 损坏的 PDF' });
    expect(useChatStore.getState().cards['abc-123']).toMatchObject({
      label: 'doc',
      error: '解析失败: 损坏的 PDF',
      link: '/sources/doc/abc-123',
    });
  });

  it('repo-style payloads without kind still link source_id to the repo detail page', () => {
    dispatch('task.failed', { source_id: 'r-1', error: 'clone 超时' });
    expect(useChatStore.getState().cards['r-1']?.link).toBe('/sources/repo/r-1');
  });

  it('graph job_ids have no detail page, so no link is fabricated', () => {
    dispatch('task.progress', { job_id: 'g-1', project: 'demo', stage: 'start' });
    expect(useChatStore.getState().cards['g-1']?.link).toBeUndefined();
  });

  it('progress then completed: label kept, progress filled, stage does not reuse the old running value', () => {
    dispatch('task.progress', { job_id: 'g-2', project: 'demo', stage: 'start', progress: 0.2 });
    dispatch('task.completed', { job_id: 'g-2', project: 'demo', progress: 1.0 });
    expect(useChatStore.getState().cards['g-2']).toMatchObject({
      label: 'demo',
      stage: '已完成',
      status: 'completed',
      progress: 1,
    });
  });

  it('enqueued without a stage gets the zh fallback copy instead of a technical term', () => {
    dispatch('task.enqueued', { job_id: 'g-3', project: 'demo' });
    expect(useChatStore.getState().cards['g-3']?.stage).toBe('进行中');
  });

  it('note.created appends an artifact and empty note_ids are filtered', () => {
    dispatch('note.created', { note_id: 'n-1', title: '会议纪要' });
    dispatch('note.created', { note_id: '', title: '占位' });
    expect(useChatStore.getState().artifacts.map((a) => a.noteId)).toEqual(['n-1']);
  });

  it('the card set is capped: oldest settled cards are evicted first', () => {
    for (let i = 0; i < 40; i++) {
      dispatch('task.completed', { job_id: `j-${i}`, project: 'demo' });
    }
    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    expect(cards['j-0']).toBeUndefined();
    expect(cardOrder[0]).toBe('j-10');
    expect(cards['j-39']).toBeDefined();
  });

  it('a running card survives cap eviction while newer settled cards are dropped', () => {
    for (let i = 0; i < 40; i++) {
      dispatch('task.completed', { job_id: `j-${i}`, project: 'demo' });
    }
    dispatch('task.progress', { job_id: 'live-1', project: 'demo' });
    for (let i = 40; i < 70; i++) {
      dispatch('task.completed', { job_id: `j-${i}`, project: 'demo' });
    }
    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    expect(cards['live-1']).toMatchObject({ status: 'running' });
    expect(cards['j-11']).toBeUndefined();
    expect(cards['j-69']).toBeDefined();
  });
});

describe('chatStore tool step visibility (phase-06)', () => {
  it('agent.step sets the current step; a new step overrides the old one', () => {
    dispatch('agent.step', { subagent: 'chat', name: 'activate_tools', kind: 'tool', summary: '' });
    expect(useChatStore.getState().currentStep).toMatchObject({
      name: 'activate_tools',
      subagent: 'chat',
    });
    dispatch('agent.step', { subagent: 'chat', name: 'notes__create_note', kind: 'tool' });
    expect(useChatStore.getState().currentStep?.name).toBe('notes__create_note');
  });

  it('agent.message (the round produced output) clears the current step', () => {
    dispatch('agent.step', { subagent: 'chat', name: 'notes__create_note' });
    dispatch('agent.message', { content: '笔记写好了' });
    expect(useChatStore.getState().currentStep).toBeNull();
  });
});

describe('TaskCards rendering', () => {
  it('a failed card shows the error copy; cards with a link navigate to the source page on click', () => {
    useChatStore.setState({
      cards: {
        'abc-123': card({
          key: 'abc-123',
          label: 'doc',
          stage: 'parse',
          status: 'failed',
          error: '解析失败: 损坏的 PDF',
          link: '/sources/doc/abc-123',
        }),
      },
      cardOrder: ['abc-123'],
    });
    render(
      <MemoryRouter>
        <TaskCards />
      </MemoryRouter>
    );
    expect(screen.getByText(/解析失败: 损坏的 PDF/)).toBeInTheDocument();
    expect(screen.getByRole('link')).toHaveAttribute('href', '/sources/doc/abc-123');
  });
});

describe('note artifact inline preview', () => {
  it('expanding fetches the full text via notes.get_note and renders Markdown; clicking again collapses', async () => {
    callCapabilityMock.mockResolvedValue({
      title: '会议纪要',
      content: '# 标题行\n\n正文段落',
    });
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-1', title: '会议纪要' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /会议纪要/ }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('notes', 'get_note', { note_id: 'n-1' })
    );
    expect(await screen.findByRole('heading', { name: '标题行' })).toBeInTheDocument();
    // the jump-to-notes-page entry is preserved
    expect(screen.getByRole('link', { name: '笔记页 →' })).toHaveAttribute(
      'href',
      '/notes?note=n-1'
    );
    // collapse
    fireEvent.click(screen.getByRole('button', { name: /会议纪要/ }));
    expect(screen.queryByRole('heading', { name: '标题行' })).not.toBeInTheDocument();
  });

  it('collapse then expand does not re-request the full text (already-loaded cache)', async () => {
    callCapabilityMock.mockResolvedValue({ title: 't', content: '正文' });
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-2', title: 't' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    await screen.findByText('正文');
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    fireEvent.click(screen.getByRole('button', { name: /已创建笔记/ }));
    await screen.findByText('正文');
    expect(callCapabilityMock).toHaveBeenCalledTimes(1);
  });

  it('a deleted note (NOT_FOUND) shows a visible explanation instead of a blank', async () => {
    callCapabilityMock.mockRejectedValue(new ServiceError('notes.NOT_FOUND', '笔记不存在: n-9'));
    useChatStore.setState({ artifacts: [{ seq: 1, noteId: 'n-9', title: '被删的笔记' }] });
    render(
      <MemoryRouter>
        <MessageList />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: /被删的笔记/ }));
    expect(await screen.findByText(/笔记不存在或已被删除/)).toBeInTheDocument();
  });
});
