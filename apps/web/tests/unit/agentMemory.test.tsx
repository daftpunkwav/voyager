/**
 * @file agentMemory
 * @description Settings page memory section unit tests (phase-08): the
 * profile summary is visible, clear-all goes through
 * agent.clear_memory(zone=all), and getApi() is never called (the old
 * clearUserMemory→recall_memory dead link has been removed).
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, it, expect, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { callCapabilityMock, getApiMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  getApiMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

// Any call to getApi fails the test: the memory section must go through callCapability
vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { MemoryBlock } from '@/components/settings/agent/MemoryBlock';
import { MemoryRetentionBlock } from '@/components/settings/agent/MemoryRetentionBlock';
import { useUIStore } from '@/stores/uiStore';

const SNAPSHOT = {
  profile: {
    summary: '- 语言偏好: 中文\n- 学习目标: langgraph',
    items: [{ key: '语言偏好', value: '中文' }],
  },
  episodic: {
    recent: [{ id: 1, ts: 1756500000, kind: 'consider', summary: '用户在看 langgraph' }],
    shown: 1,
  },
  semantic: { recent: [], shown: 0 },
  working: { size: 3 },
  retention_days: 90,
  purged_episodic: 0,
};

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'memory': {
      const action = String(args.action ?? 'query');
      if (action === 'query') return Promise.resolve(SNAPSHOT);
      if (action === 'clear') {
        const zone = String(args.zone);
        return Promise.resolve({ zone, cleared: { [zone]: 4 } });
      }
      return Promise.resolve({ ok: true });
    }
    case 'get_setting':
      return Promise.resolve({ value: args.key === 'agent.memory.retention_days' ? 90 : '热心' });
    case 'set_setting':
      return Promise.resolve({ value: args.value });
    default:
      return Promise.resolve({});
  }
}

function renderSection() {
  render(
    <>
      <MemoryBlock />
      <MemoryRetentionBlock />
    </>
  );
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('settings page memory section (phase-08)', () => {
  it('renders the profile summary and key-values (no getApi call)', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText(/语言偏好: 中文/)).toBeTruthy());
    expect(screen.getByText('中文')).toBeTruthy();
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('shows a confirm dialog on clear-all and calls clear_memory with zone=all after confirming', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText(/语言偏好: 中文/)).toBeTruthy());

    fireEvent.click(screen.getByTestId('clear-memory-all-btn'));
    const dialog = screen.getByRole('dialog');
    // The confirm copy states that the timeline/notes/projects are preserved
    expect(within(dialog).getByText(/对话时间线、笔记与项目会保留/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'memory', {
      action: 'clear',
      zone: 'all',
    });

    // Scope with within(dialog): the working-memory section on the page also has a "clear" button with the same name
    fireEvent.click(within(dialog).getByRole('button', { name: '清空' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'memory', {
        action: 'clear',
        zone: 'all',
      })
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true)
    );
  });

  it('deleting a profile key calls memory(forget) and refetches memory(query) on success', async () => {
    renderSection();
    await waitFor(() => expect(screen.getByText('中文')).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: '删除' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'memory', {
        action: 'forget',
        key: '语言偏好',
      })
    );
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'memory', { action: 'query' })
    );
  });

  it('retention days read/write goes through settings.set_setting / get_setting', async () => {
    renderSection();
    const input = (await screen.findByLabelText('情节记忆保留天数')) as HTMLInputElement;
    // The draft starts empty and fills after the async get_setting resolves;
    // asserting right after mount is a race on slow/loaded CI runners.
    await waitFor(() => expect(input.value).toBe('90'));

    fireEvent.change(input, { target: { value: '30' } });
    fireEvent.blur(input);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.memory.retention_days',
        value: 30,
      })
    );
  });
});
