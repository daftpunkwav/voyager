/**
 * @file chatHistoryPaging
 * @description Backward chat-history paging (2026-09): the newest-window initial
 * load plus scroll-to-top "load earlier" — store windowing, the MessageList
 * trigger, and the no-progress stop guard.
 */

import { fireEvent, render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchChatHistoryBeforeMock } = vi.hoisted(() => ({
  fetchChatHistoryBeforeMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/chatSend')>()),
  fetchChatHistoryBefore: fetchChatHistoryBeforeMock,
}));

import { MessageList } from '@/widgets/chat/MessageList';
import { useChatStore, type ChatEvent } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function row(seq: number, content: string): ChatEvent {
  return { seq, type: 'user.message', payload: { content } };
}

beforeAll(() => {
  initI18n();
  // jsdom gap: MessageList's scroll effects need matchMedia / scrollIntoView
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
  fetchChatHistoryBeforeMock.mockReset();
  useChatStore.setState({
    messages: [],
    hasMoreHistory: false,
    historyLoading: false,
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    thinking: false,
    connected: true,
    currentStep: null,
    streaming: null,
  });
});

describe('chatStore backward paging', () => {
  it('applyHistory records hasMoreHistory alongside the newest window', () => {
    useChatStore.getState().applyHistory([row(30, 'a'), row(31, 'b')], true);
    const s = useChatStore.getState();
    expect(s.messages.map((m) => m.seq)).toEqual([30, 31]);
    expect(s.hasMoreHistory).toBe(true);
  });

  it('prependHistory puts the older page in front and clears the loading flag', () => {
    useChatStore.setState({
      messages: [
        { seq: 30, role: 'user', content: 'a' },
        { seq: -999, role: 'system', content: 'local bubble' },
      ],
      historyLoading: true,
    });
    useChatStore.getState().prependHistory([row(28, 'x'), row(29, 'y')], true);
    const s = useChatStore.getState();
    expect(s.messages.map((m) => m.seq)).toEqual([28, 29, 30, -999]);
    expect(s.historyLoading).toBe(false);
    expect(s.hasMoreHistory).toBe(true);
  });

  it('prependHistory drops duplicate seqs (overlapping window)', () => {
    useChatStore.setState({ messages: [{ seq: 30, role: 'user', content: 'a' }] });
    useChatStore.getState().prependHistory([row(29, 'y'), row(30, 'dup')], false);
    expect(useChatStore.getState().messages.map((m) => m.seq)).toEqual([29, 30]);
  });

  it('prependHistory merges agent.delivery rows from the older page (dedup by seq)', () => {
    const delivery = (seq: number): ChatEvent => ({
      seq,
      type: 'agent.delivery',
      payload: { member: 'explainer', name: 'run', title: 't', status: 'done', content: 'c' },
    });
    useChatStore.setState({
      messages: [{ seq: 30, role: 'user', content: 'a' }],
      deliveries: [{ seq: 3001, member: 'recon', name: 'r', title: 'x', status: 'failed', content: '' }],
    });
    useChatStore
      .getState()
      .prependHistory([row(28, 'x'), delivery(2001), delivery(3001)], false);
    const s = useChatStore.getState();
    expect(s.deliveries.map((d) => d.seq)).toEqual([2001, 3001]);
    expect(s.deliveries[0].member).toBe('explainer');
    expect(s.deliveries[1].member).toBe('recon');
  });
});

describe('MessageList scroll-to-top loader', () => {
  function mountInScroller() {
    const host = render(
      <div style={{ overflowY: 'auto', height: 300 }}>
        <MemoryRouter>
          <MessageList />
        </MemoryRouter>
      </div>
    );
    return host.container.firstElementChild as HTMLElement;
  }

  it('scrolling to the top fetches the page before the oldest seq and prepends it', async () => {
    useChatStore.setState({
      messages: [
        { seq: 30, role: 'user', content: 'a' },
        { seq: 31, role: 'agent', content: 'b' },
      ],
      hasMoreHistory: true,
    });
    fetchChatHistoryBeforeMock.mockResolvedValue({
      messages: [row(28, 'x'), row(29, 'y')],
      hasMore: false,
    });
    const scroller = mountInScroller();
    fireEvent.scroll(scroller);
    await waitFor(() => {
      // Paging passes the active session: before_seq pages the global log and
      // would otherwise pull other sessions' rows into this lane
      expect(fetchChatHistoryBeforeMock).toHaveBeenCalledWith(30, 200, undefined);
    });
    await waitFor(() => {
      const s = useChatStore.getState();
      expect(s.messages.map((m) => m.seq)).toEqual([28, 29, 30, 31]);
      expect(s.historyLoading).toBe(false);
      expect(s.hasMoreHistory).toBe(false);
    });
  });

  it('does not fetch while a load is in flight or no older pages exist', () => {
    useChatStore.setState({ messages: [{ seq: 30, role: 'user', content: 'a' }] });
    const scroller = mountInScroller();
    fireEvent.scroll(scroller);
    expect(fetchChatHistoryBeforeMock).not.toHaveBeenCalled();

    useChatStore.setState({ hasMoreHistory: true, historyLoading: true });
    fireEvent.scroll(scroller);
    expect(fetchChatHistoryBeforeMock).not.toHaveBeenCalled();
  });

  it('a page with only duplicates stops the load offer (no endless retry loop)', async () => {
    useChatStore.setState({
      messages: [{ seq: 30, role: 'user', content: 'a' }],
      hasMoreHistory: true,
    });
    fetchChatHistoryBeforeMock.mockResolvedValue({
      messages: [row(30, 'dup')],
      hasMore: true,
    });
    const scroller = mountInScroller();
    fireEvent.scroll(scroller);
    await waitFor(() => {
      const s = useChatStore.getState();
      expect(s.historyLoading).toBe(false);
      expect(s.hasMoreHistory).toBe(false);
    });
    // Scrolling again offers nothing further
    fireEvent.scroll(scroller);
    expect(fetchChatHistoryBeforeMock).toHaveBeenCalledTimes(1);
  });
});
