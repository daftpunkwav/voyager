/**
 * @file agentUserHooks
 * @description Settings page user hooks block unit tests (phase-78):
 * mounting calls list_user_hooks and renders file names / on / disabled and
 * not-loaded states, the empty-state guidance, "reload" calling
 * reload_user_hooks, the success toast including the loaded count, skipped
 * disclosure, the failure toast, and the busy guard against double submit;
 * getApi() is never called.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { UserHooksBlock } from '@/components/settings/agent/UserHooksBlock';
import { WorkspaceBlock } from '@/components/settings/agent/WorkspaceBlock';
import { useUIStore } from '@/stores/uiStore';

const SNAPSHOT = {
  profile: { summary: '', items: [] },
  episodic: { recent: [], shown: 0 },
  semantic: { recent: [], shown: 0 },
  working: { size: 0 },
  retention_days: 90,
  purged_episodic: 0,
};

/** Keyed settings store (same approach as the existing settings page tests to avoid failing other blocks) */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.workspace.dir': 'workspace',
};

const HOOKS = [
  {
    path: 'note-watch.json',
    on: 'note.created',
    enabled: true,
    description: '笔记新建',
    loaded: true,
  },
  {
    path: 'offline.json',
    on: 'note.deleted',
    enabled: false,
    description: '已停用示例',
    loaded: false,
  },
];

function backend(
  overrides: { items?: unknown[]; failList?: boolean; failReload?: boolean; reload?: object } = {}
) {
  return (_domain: string, name: string, _args: Record<string, unknown>) => {
    switch (name) {
      case 'list_user_hooks':
        if (overrides.failList) return Promise.reject(new Error('boom'));
        return Promise.resolve({ items: overrides.items ?? HOOKS });
      case 'reload_user_hooks':
        if (overrides.failReload) return Promise.reject(new Error('user operations only'));
        return Promise.resolve({
          loaded: 2,
          event_patterns: ['note.created'],
          ...overrides.reload,
        });
      case 'get_memory':
        return Promise.resolve(SNAPSHOT);
      case 'get_setting':
        return Promise.resolve({ value: SETTINGS[String(_args.key)] });
      default:
        return Promise.resolve({});
    }
  };
}

function renderSection(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(
    <>
      <UserHooksBlock />
      <WorkspaceBlock />
    </>
  );
}

const toastTexts = () => useUIStore.getState().toasts.map((t) => t.message);

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('settings page user hooks block (phase-78)', () => {
  it('mounts with list_user_hooks and renders file names / on / disabled and not-loaded states; no getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('note-watch.json')).toBeTruthy());
    expect(screen.getByText('offline.json')).toBeTruthy();
    expect(screen.getByText('note.created')).toBeTruthy();
    // status chips render separately (path + trigger chip + state chips)
    expect(screen.getByText('note.deleted')).toBeTruthy();
    expect(screen.getByText('已停用')).toBeTruthy();
    expect(screen.getByText('未装载')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_user_hooks', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('empty list shows placement guidance (directory and reload after editing files)', async () => {
    renderSection(backend({ items: [] }));
    await waitFor(() => expect(screen.getByText(/hooks\/ 下/)).toBeTruthy());
  });

  it('on load failure shows only the block-level "reload" hint while the other sections stay intact', async () => {
    renderSection(backend({ failList: true }));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    expect(screen.getByLabelText('工作目录')).toBeTruthy();
  });

  it('"reload" calls reload_user_hooks; the success toast includes the loaded count and the list refreshes', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'reload_user_hooks', {})
    );
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.includes('已重新加载用户钩子') && m.includes('装载 2 个'))
      ).toBe(true)
    );
    // after reload succeeds, list_user_hooks is called again to refresh the list
    const listCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'list_user_hooks');
    expect(listCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('when the response carries skipped, the toast discloses the skipped files and reasons', async () => {
    renderSection(
      backend({
        reload: { skipped: [{ path: 'broken.json', reason: '无法解析: 坏 JSON' }] },
      })
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('broken.json') && m.includes('坏 JSON'))).toBe(
        true
      )
    );
  });

  it('reload failure fires an error toast (copy includes the backend-readable message)', async () => {
    renderSection(backend({ failReload: true }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.startsWith('重载失败：') && m.includes('user operations only'))
      ).toBe(true)
    );
  });

  it('busy guard against double submit: the button is disabled while the request is pending and double click sends once', async () => {
    let resolveReload!: (v: unknown) => void;
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, _args: Record<string, unknown>) => {
        if (name === 'list_user_hooks') return Promise.resolve({ items: HOOKS });
        if (name === 'reload_user_hooks') {
          return new Promise((resolve) => {
            resolveReload = resolve;
          });
        }
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      }
    );
    render(
      <>
        <UserHooksBlock />
      </>
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '重新加载用户钩子' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' }));
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: '重新加载用户钩子' }) as HTMLButtonElement).disabled
      ).toBe(true)
    );
    fireEvent.click(screen.getByRole('button', { name: '重新加载用户钩子' })); // a disabled button does not send again
    const reloadCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'reload_user_hooks');
    expect(reloadCalls).toHaveLength(1);
    resolveReload({ loaded: 2, event_patterns: [] });
    await waitFor(() =>
      expect(
        (screen.getByRole('button', { name: '重新加载用户钩子' }) as HTMLButtonElement).disabled
      ).toBe(false)
    );
  });
});
