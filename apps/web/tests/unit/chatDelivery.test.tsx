/**
 * @file chatDelivery
 * @description Team delivery cards: agent.delivery lands as a structured
 * card (member head + name + status + collapsible Markdown), long bodies fold
 * behind an expander, failures render the error with the run pointer, and
 * control-plane notices render as Markdown instead of a raw text blob.
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

vi.mock('@/bridge/stream', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/stream')>()),
  subscribe: subscribeMock,
}));

import { MessageList } from '@/widgets/chat/MessageList';
import { useChatStream } from '@/hooks/useChatStream';
import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function resetStore() {
  useChatStore.setState({
    messages: [],
    deliveries: [],
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
});

function renderStream() {
  return render(
    <MemoryRouter>
      <MessageList />
    </MemoryRouter>
  );
}

function deliveryEvent(over: Record<string, unknown> = {}): ChatEvent {
  return {
    seq: 3001,
    type: 'agent.delivery',
    ts: 1700000000,
    payload: {
      member: 'explainer',
      name: 'explainer-run',
      title: '讲 real-mock',
      status: 'done',
      content: '# RealMock\n\nAI 模拟面试平台,上传简历获得解析与深度评审。',
      run_id: 'run-77',
      elapsed_s: 42,
      ...over,
    },
  };
}

describe('team delivery cards (MessageList)', () => {
  it('renders a done delivery as a card with member, badge, and markdown body', () => {
    useChatStore.getState().dispatch(deliveryEvent());
    renderStream();
    expect(screen.getByText('Elio')).toBeTruthy();
    expect(screen.getByText('完成')).toBeTruthy();
    expect(screen.getByText('讲 real-mock')).toBeTruthy();
    expect(screen.getByText(/AI 模拟面试平台/)).toBeTruthy();
    expect(screen.getByText(/42 秒/)).toBeTruthy();
  });

  it('dedupes by seq: a replayed frame does not duplicate the card', () => {
    const store = useChatStore.getState();
    store.dispatch(deliveryEvent());
    store.dispatch(deliveryEvent());
    expect(useChatStore.getState().deliveries.length).toBe(1);
  });

  it('folds a long body and expands on click', () => {
    const long = '很长的讲解。'.repeat(400);
    useChatStore.getState().dispatch(deliveryEvent({ content: long }));
    renderStream();
    expect(screen.getByText(/很长的讲解。/)).toBeTruthy();
    expect(screen.queryByText(long)).toBeNull(); // folded
    fireEvent.click(screen.getByText('展开全文'));
    expect(screen.getByText(long)).toBeTruthy(); // expanded in full
  });

  it('renders a failed delivery with the error and keeps the run pointer', () => {
    useChatStore.getState().dispatch(
      deliveryEvent({
        status: 'failed',
        content: '',
        error: 'ValueError: bad input',
      })
    );
    renderStream();
    expect(screen.getByText('失败')).toBeTruthy();
    expect(screen.getByText(/ValueError: bad input/)).toBeTruthy();
    // run drill-in is wired through the panel; the card keeps the pointer
    expect(useChatStore.getState().deliveries[0].run_id).toBe('run-77');
  });

  it('control-plane notices render as markdown, not a raw blob', () => {
    useChatStore.setState({
      messages: [
        {
          seq: 4001,
          role: 'agent',
          content: '[paused] 已暂停\n\n**用 resume_run 继续**',
          kind: 'notice',
        },
      ],
    });
    renderStream();
    expect(screen.getByText(/resume_run/)).toBeTruthy(); // markdown strong/em/code path
    expect(screen.queryByText(/\*\*用 resume_run 继续\*\*/)).toBeNull();
  });
});

describe('live delivery wiring (useChatStream)', () => {
  /** Probe component that mounts the stream hook (onNavigate unused here). */
  function HookProbe() {
    useChatStream(() => {});
    return null;
  }

  /** The event callback useChatStream registers into subscribe. */
  function handler() {
    return subscribeMock.mock.calls[0][1] as (ev: ChatEvent) => void;
  }

  beforeEach(() => {
    subscribeMock.mockClear();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [], has_more: false }),
      } as Response)
    );
  });

  it('subscribes to agent.delivery so a live card lands without a refresh', () => {
    render(
      <MemoryRouter>
        <HookProbe />
      </MemoryRouter>
    );
    const patterns = subscribeMock.mock.calls[0][0] as string[];
    expect(patterns).toContain('agent.delivery');
  });

  it('a live agent.delivery frame reaches the store, idempotent on replay', () => {
    render(
      <MemoryRouter>
        <HookProbe />
      </MemoryRouter>
    );
    handler()(deliveryEvent());
    handler()(deliveryEvent()); // reconnect replay: dedup by seq keeps one card
    expect(useChatStore.getState().deliveries).toHaveLength(1);
    expect(useChatStore.getState().deliveries[0].title).toBe('讲 real-mock');
  });
});
