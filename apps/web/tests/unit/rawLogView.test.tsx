/**
 * @file rawLogView
 * @description Characterization tests for the chat page's raw log tab: the
 * recorded rounds are listed collapsed, the header toggle and the tab bar
 * reveal the recorded bodies, the wire body only exists for rounds recorded
 * with it, and the tab shows the load / empty / error states.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchRawLlmRoundsMock } = vi.hoisted(() => ({
  fetchRawLlmRoundsMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/chatSend')>()),
  fetchRawLlmRounds: fetchRawLlmRoundsMock,
}));

import { RawLogView } from '@/widgets/chat/RawLogView';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';
import type { RawLlmRound } from '@/bridge/chatSend';

/** The header toggle's accessible name (also its tooltip). */
const TOGGLE_NAME = '展开或收起这一轮的原始请求与响应';

function round(over: Partial<RawLlmRound> = {}): RawLlmRound {
  return {
    run_id: 'run-1',
    round: 1,
    session: 's-1',
    ts: 1700000000,
    request: '{"messages":[{"role":"user","content":"hi"}]}',
    response: '{"ok":true}',
    ...over,
  };
}

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  useChatStore.setState({ activeSessionId: 's-1' });
  fetchRawLlmRoundsMock.mockReset();
});

describe('RawLogView', () => {
  it('lists the loaded rounds collapsed and fetches only the rendered window', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [round()], total: 1 });
    render(<RawLogView />);

    expect(await screen.findByText(/轮 1/)).toBeTruthy();
    // The body stays hidden until the round is inspected.
    expect(screen.queryByText(/"messages"/)).toBeNull();
    // No wire body was recorded for this round, so no wire tab is offered.
    expect(screen.queryByRole('tab', { name: '请求体' })).toBeNull();
    expect(fetchRawLlmRoundsMock).toHaveBeenCalledWith('s-1', 50);
  });

  it('reveals the request body when the round is expanded', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [round()], total: 1 });
    render(<RawLogView />);

    fireEvent.click(await screen.findByRole('button', { name: TOGGLE_NAME }));
    expect(await screen.findByText(/"messages"/)).toBeTruthy();
  });

  it('switches to the picked body and expands the round with it', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [round()], total: 1 });
    render(<RawLogView />);

    fireEvent.click(await screen.findByRole('tab', { name: '响应' }));
    expect(await screen.findByText(/"ok": true/)).toBeTruthy();
    expect(screen.queryByText(/"messages"/)).toBeNull();

    // Switching panes on an open card keeps it open.
    fireEvent.click(screen.getByRole('tab', { name: '请求' }));
    expect(await screen.findByText(/"messages"/)).toBeTruthy();
    expect(screen.queryByText(/"ok": true/)).toBeNull();
  });

  it('opens on the wire body of rounds recorded with one', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({
      rounds: [round({ wire_request: '{"stream":true}' })],
      total: 1,
    });
    render(<RawLogView />);

    const wireTab = await screen.findByRole('tab', { name: '请求体' });
    expect(wireTab.getAttribute('aria-selected')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: TOGGLE_NAME }));
    expect(await screen.findByText(/"stream": true/)).toBeTruthy();
  });

  it('reports the rounds that stayed out of the rendered window', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [round()], total: 12 });
    render(<RawLogView />);

    expect(await screen.findByText(/已跳过较早的 11 轮/)).toBeTruthy();
  });

  it('shows the empty state when the session recorded no rounds', async () => {
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [], total: 0 });
    render(<RawLogView />);

    expect(await screen.findByText('该轮没有原始记录')).toBeTruthy();
  });

  it('shows the load error instead of the round list', async () => {
    fetchRawLlmRoundsMock.mockRejectedValue(new Error('HTTP 500'));
    render(<RawLogView />);

    expect(await screen.findByText(/HTTP 500/)).toBeTruthy();
  });

  it('does not fetch without an active session and shows the empty state', async () => {
    useChatStore.setState({ activeSessionId: '' });
    fetchRawLlmRoundsMock.mockResolvedValue({ rounds: [round()], total: 1 });
    render(<RawLogView />);

    expect(await screen.findByText('该轮没有原始记录')).toBeTruthy();
    expect(fetchRawLlmRoundsMock).not.toHaveBeenCalled();
  });
});
