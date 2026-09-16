/**
 * @file agentMcp
 * @description Settings page external MCP unit tests (phase-11b): mounting
 * calls list_mcp_servers; add/approve/remove hit the corresponding
 * capabilities; getApi() is never called. GlassSelect is not tested directly
 * (the stdio default + whole-package approval covers the submission).
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

vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { McpBlock } from '@/components/settings/agent/McpBlock';
import { RoundsBlock } from '@/components/settings/agent/RoundsBlock';
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
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
};

/** list_mcp_servers sample: unapproved, connected, per-item approval, with preview */
const SERVER = {
  id: 'my-search',
  name: 'My Search',
  kind: 'stdio',
  command: 'npx',
  args: ['-y', 'x'],
  url: '',
  approval: 'item',
  approved: [],
  enabled: true,
  connected: true,
  error: '',
  preview: [
    { name: 'search', description: '搜索' },
    { name: 'fetch', description: '抓取' },
  ],
  mounted: [],
};

function backend(overrides: Record<string, unknown> = {}) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_mcp_servers':
        return Promise.resolve(overrides.list_mcp_servers ?? [{ ...SERVER, ...overrides.server }]);
      case 'add_mcp_server':
        return Promise.resolve({ ok: true, id: args.id, connected: true, error: '', preview: [] });
      case 'approve_mcp_tools':
        return Promise.resolve({
          ok: true,
          approved: args.names,
          mounted: ['mcp__my-search__search'],
        });
      case 'remove_mcp_server':
        return Promise.resolve({ ok: true });
      case 'preview_mcp_tools':
        return Promise.resolve({ id: args.id, preview: SERVER.preview });
      case 'get_memory':
        return Promise.resolve(SNAPSHOT);
      case 'get_setting':
        return Promise.resolve({ value: SETTINGS[String(args.key)] });
      default:
        return Promise.resolve({});
    }
  };
}

function renderSection(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(
    <>
      <McpBlock />
      <RoundsBlock />
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

describe('settings page external MCP (phase-11b)', () => {
  it('mounts with list_mcp_servers and renders the name/unapproved/preview tools; no getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('My Search')).toBeTruthy());
    expect(screen.getByText(/未批准/)).toBeTruthy();
    // Assert the preview list via the per-item checkbox's unique aria-label (descriptions would collide with the network permission block)
    expect(screen.getByLabelText('my-search · search')).toBeTruthy();
    expect(screen.getByLabelText('my-search · fetch')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_mcp_servers', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('an empty list shows the add guidance', async () => {
    renderSection(backend({ list_mcp_servers: [] }));
    await waitFor(() => expect(screen.getByText(/还没有外接 MCP/)).toBeTruthy());
  });

  it('a connection failure shows the per-entry error without taking down the page', async () => {
    renderSection(backend({ server: { connected: false, error: '连接被拒(测试)' } }));
    await waitFor(() => expect(screen.getByText(/连接被拒/)).toBeTruthy());
    // Other sections stay intact: the rounds input is still queryable
    expect(screen.getByLabelText('ReAct 轮数上限')).toBeTruthy();
  });

  it('filling the id and submitting → add_mcp_server carries the form fields; the success toast mentions when it becomes visible', async () => {
    renderSection(backend({ list_mcp_servers: [] }));
    await waitFor(() => expect(screen.getByLabelText('MCP id')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('MCP id'), { target: { value: 'my-search' } });
    fireEvent.change(screen.getByLabelText('MCP command'), { target: { value: 'npx' } });
    fireEvent.change(screen.getByLabelText('MCP args'), { target: { value: '-y\nx' } });
    fireEvent.click(screen.getByRole('button', { name: '添加 MCP' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'add_mcp_server', {
        id: 'my-search',
        name: 'my-search',
        kind: 'stdio',
        command: 'npx',
        args: ['-y', 'x'],
        url: '',
        approval: 'package',
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('下一句或新对话可见'))).toBe(true)
    );
  });

  it('per-item: checking a tool then "approve selected" → approve carries the checked names; the approval toast says it is visible next turn', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByLabelText('my-search · search')).toBeTruthy());
    fireEvent.click(screen.getByLabelText('my-search · search'));
    fireEvent.click(screen.getByRole('button', { name: '批准所选 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'approve_mcp_tools', {
        id: 'my-search',
        names: ['search'],
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('下一句或新对话可见'))).toBe(true)
    );
  });

  it('whole package: "approve all" → approve names=["*"]', async () => {
    renderSection(backend({ server: { approval: 'package' } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '批准全部 My Search' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '批准全部 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'approve_mcp_tools', {
        id: 'my-search',
        names: ['*'],
      })
    );
  });

  it('"refresh tool list" → preview_mcp_tools', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '刷新工具列表 My Search' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '刷新工具列表 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'preview_mcp_tools', {
        id: 'my-search',
      })
    );
  });

  it('"remove" goes through a confirm dialog and hits remove_mcp_server after confirming', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '移除 My Search' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '移除 My Search' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/确定移除/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '移除' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'remove_mcp_server', {
        id: 'my-search',
      })
    );
  });
});
