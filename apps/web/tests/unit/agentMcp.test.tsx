/**
 * @file agentMcp
 * @description Settings page external MCP unit tests: mounting calls
 * list_mcp_servers; adding happens in the dialog (add_mcp_server); tool
 * preview + per-item/package approval live in the expandable row; remove hits
 * remove_mcp_server behind a confirmation; getApi() is never called.
 * GlassSelect is not tested directly (the stdio default + whole-package
 * approval covers the submission).
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
import { useUIStore } from '@/stores/uiStore';

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
      case 'extension':
        if (args.kind === 'mcp' && args.action === 'list') {
          return Promise.resolve(
            overrides.list_mcp_servers ?? [{ ...SERVER, ...overrides.server }]
          );
        }
        if (args.kind === 'mcp' && args.action === 'preview') {
          return Promise.resolve({ id: args.id, preview: SERVER.preview });
        }
        return Promise.resolve({});
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
      default:
        return Promise.resolve({});
    }
  };
}

function renderBlock(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(<McpBlock />);
}

const toastTexts = () => useUIStore.getState().toasts.map((t) => t.message);

/** Expand the row (the tool preview area lives inside the expandable row body). */
async function expandRow(name: string) {
  await waitFor(() => expect(screen.getByText(name)).toBeTruthy());
  fireEvent.click(screen.getByText(name));
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('settings page external MCP', () => {
  it('mounts with extension(mcp list) and renders the name/unapproved chip; no getApi()', async () => {
    renderBlock(backend());
    await waitFor(() => expect(screen.getByText('My Search')).toBeTruthy());
    expect(screen.getByText('未批准')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
      kind: 'mcp',
      action: 'list',
    });
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('an empty list shows the add guidance', async () => {
    renderBlock(backend({ list_mcp_servers: [] }));
    // The EmptyState title and description both carry the guidance phrase
    await waitFor(() => expect(screen.getAllByText(/还没有外接 MCP/).length).toBeGreaterThan(0));
  });

  it('a connection failure shows the per-entry error without taking down the block', async () => {
    renderBlock(backend({ server: { connected: false, error: '连接被拒(测试)' } }));
    await waitFor(() => expect(screen.getByText(/连接被拒/)).toBeTruthy());
    expect(screen.getByText('未连接')).toBeTruthy();
  });

  it('creating via the dialog: 新建 → fill → add_mcp_server carries the form fields; the success toast mentions when it becomes visible', async () => {
    renderBlock(backend({ list_mcp_servers: [] }));
    await waitFor(() => expect(screen.getByRole('button', { name: '+ 新建' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '+ 新建' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('MCP id'), { target: { value: 'my-search' } });
    fireEvent.change(within(dialog).getByLabelText('MCP command'), { target: { value: 'npx' } });
    fireEvent.change(within(dialog).getByLabelText('MCP args'), { target: { value: '-y\nx' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '添加 MCP' }));
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

  it('per-item: expanding the row, checking a tool then "approve selected" → approve carries the checked names', async () => {
    renderBlock(backend());
    await expandRow('My Search');
    expect(screen.getByLabelText('my-search · search')).toBeTruthy();
    expect(screen.getByLabelText('my-search · fetch')).toBeTruthy();
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
    renderBlock(backend({ server: { approval: 'package' } }));
    await expandRow('My Search');
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

  it('"refresh tool list" → extension(mcp preview)', async () => {
    renderBlock(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '刷新工具列表 My Search' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '刷新工具列表 My Search' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
        kind: 'mcp',
        action: 'preview',
        id: 'my-search',
      })
    );
  });

  it('"remove" goes through a confirm dialog and hits remove_mcp_server after confirming', async () => {
    renderBlock(backend());
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
