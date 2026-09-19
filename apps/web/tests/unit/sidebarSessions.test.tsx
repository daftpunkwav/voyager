/**
 * @file sidebarSessions
 * @description Sidebar session manager interactions (chatSend and api/agent
 * are stubbed): the row menu's pin and two-step delete confirmation, rename
 * commit vs. cancel, session switching (backend activate + lane backfill),
 * and the archived section staying collapsed until toggled.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const {
  loadChatSessionsMock,
  loadSessionTimelineMock,
  pinSessionMock,
  renameSessionMock,
  deleteSessionMock,
  setActiveSessionMock,
  getContextStatusMock,
} = vi.hoisted(() => ({
  loadChatSessionsMock: vi.fn(),
  loadSessionTimelineMock: vi.fn(),
  pinSessionMock: vi.fn(),
  renameSessionMock: vi.fn(),
  deleteSessionMock: vi.fn(),
  setActiveSessionMock: vi.fn(),
  getContextStatusMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  loadChatSessions: loadChatSessionsMock,
  loadSessionTimeline: loadSessionTimelineMock,
}));

vi.mock('@/api/agent', () => ({
  createSession: vi.fn(),
  renameSession: renameSessionMock,
  deleteSession: deleteSessionMock,
  setActiveSession: setActiveSessionMock,
  pinSession: pinSessionMock,
  archiveSession: vi.fn(),
  getContextStatus: getContextStatusMock,
  compactSession: vi.fn(),
}));

import { Sidebar } from '@/shell/Sidebar';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function row(session_id: string, title: string, extra: Record<string, unknown> = {}) {
  return { session_id, title, status: 'idle', pinned: false, archived: false, ...extra };
}

const renderSidebar = () =>
  render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>
  );

const openMenu = async () => {
  fireEvent.click(await screen.findByRole('button', { name: '会话操作' }));
};

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  vi.clearAllMocks();
  loadChatSessionsMock.mockResolvedValue(undefined);
  loadSessionTimelineMock.mockResolvedValue(undefined);
  pinSessionMock.mockResolvedValue(undefined);
  renameSessionMock.mockResolvedValue(undefined);
  deleteSessionMock.mockResolvedValue(undefined);
  setActiveSessionMock.mockResolvedValue(undefined);
  getContextStatusMock.mockResolvedValue({ used_pct: 42 });
  useChatStore.setState({
    sessions: [],
    activeSessionId: '',
    activeLoaded: false,
    lanes: {},
    messages: [],
    currentStep: null,
  });
});

describe('SidebarSessions', () => {
  it('lists live sessions, keeps the archived section collapsed until toggled', async () => {
    useChatStore.setState({
      sessions: [row('s-1', '调研任务'), row('s-2', '旧会话', { archived: true })],
      activeSessionId: 's-1',
    });
    renderSidebar();
    expect(await screen.findByText('调研任务')).toBeTruthy();
    expect(screen.queryByText('旧会话')).toBeNull(); // collapsed by default
    fireEvent.click(screen.getByRole('button', { name: '归档 (1)' }));
    expect(screen.getByText('旧会话')).toBeTruthy();
    // The active session's context usage loads in the background
    expect(await screen.findByText('上下文 42%')).toBeTruthy();
  });

  it('pins from the row menu and refreshes the session list', async () => {
    useChatStore.setState({ sessions: [row('s-1', '调研任务')], activeSessionId: 's-1' });
    renderSidebar();
    await openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '置顶' }));
    await waitFor(() => expect(pinSessionMock).toHaveBeenCalledWith('s-1', true));
    // mount load + post-action refresh
    await waitFor(() => expect(loadChatSessionsMock).toHaveBeenCalledTimes(2));
  });

  it('delete needs an explicit confirmation click before calling the api', async () => {
    useChatStore.setState({ sessions: [row('s-1', '调研任务')], activeSessionId: 's-1' });
    renderSidebar();
    await openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '删除' }));
    // First click only arms the confirm item — nothing is deleted yet
    expect(deleteSessionMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('menuitem', { name: '确认删除?' }));
    await waitFor(() => expect(deleteSessionMock).toHaveBeenCalledWith('s-1'));
    await waitFor(() => expect(loadChatSessionsMock).toHaveBeenCalledTimes(2));
  });

  it('rename commits on Enter and cancels on Escape', async () => {
    useChatStore.setState({ sessions: [row('s-1', '调研任务')], activeSessionId: 's-1' });
    renderSidebar();
    await openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }));
    const input = screen.getByLabelText('重命名') as HTMLInputElement;
    expect(input.value).toBe('调研任务'); // pre-filled with the current title
    fireEvent.change(input, { target: { value: '新名字' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await waitFor(() => expect(renameSessionMock).toHaveBeenCalledWith('s-1', '新名字'));
    await waitFor(() => expect(screen.queryByLabelText('重命名')).toBeNull());

    // Escape closes the editor without persisting anything
    await openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: '重命名' }));
    fireEvent.keyDown(screen.getByLabelText('重命名'), { key: 'Escape' });
    expect(screen.queryByLabelText('重命名')).toBeNull();
    expect(renameSessionMock).toHaveBeenCalledTimes(1);
  });

  it('switching a session activates it on the backend and backfills the fresh lane', async () => {
    useChatStore.setState({
      sessions: [row('s-1', '甲'), row('s-2', '乙')],
      activeSessionId: 's-1',
      activeLoaded: true,
      lanes: {},
    });
    renderSidebar();
    fireEvent.click(await screen.findByText('乙'));
    await waitFor(() => expect(setActiveSessionMock).toHaveBeenCalledWith('s-2'));
    // The target lane has no archived view: the timeline must be backfilled
    await waitFor(() => expect(loadSessionTimelineMock).toHaveBeenCalledWith('s-2'));
    expect(useChatStore.getState().activeSessionId).toBe('s-2');
  });
});
