/**
 * @file agentPlugins
 * @description Settings page plugin block unit tests: mounting calls
 * list_plugins and renders name/version/approval state/permission details;
 * the approval switch hits bundle approve / revoke; per-item approval lives in
 * the expandable row picker; install runs in the dialog (zip / local dir /
 * overwrite confirm); delete confirms then uninstalls; success/failure toasts;
 * getApi() is never called.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, it, expect, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { callCapabilityMock, getApiMock, uploadFileMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  getApiMock: vi.fn(),
  uploadFileMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
  uploadFile: uploadFileMock,
}));

vi.mock('@/api/client', () => ({ getApi: getApiMock }));

import { PluginsBlock } from '@/components/settings/agent/PluginsBlock';
import { stubConfirm } from './helpers/stubConfirm';
import { useUIStore } from '@/stores/uiStore';

/** list_plugins sample: unapproved, 2 skills + 1 hook + 1 MCP */
const PLUGIN = {
  name: 'example',
  version: '0.1.0',
  description: '最小插件示例',
  approved: false,
  granularity: '',
  permissions: { scopes: ['notes.write'], network: 'off', fs: 'none' },
  contains: { skills: 2, hooks: 1, mcp: true },
  skills: [
    { name: 'daily-note', approved: false },
    { name: 'weekly-review', approved: false },
  ],
  hooks: [
    { path: 'hooks/on-note-created.json', on: 'note.created', enabled: true, approved: false },
  ],
  mcp: [{ id: 'example-search', approved: false, registered: false, tools_approved: [] }],
  path: 'example',
};

/** Result payload: skills is an array (names of loaded skills) */
const RESULT = {
  name: 'example',
  approved: true,
  granularity: 'item',
  loaded: { skills: ['daily-note'], hooks: 1, mcp_registered: 1, mcp_skipped: false },
  skipped: { skills: [], hooks: [], mcp: [] },
};

function backend(
  overrides: Record<string, unknown> = {},
  failList = false,
  failApproval = false,
  failInstall = false
) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'extension':
        if (args.kind === 'plugin' && args.action === 'list') {
          if (failList) return Promise.reject(new Error('boom'));
          return Promise.resolve({
            items: overrides.items ?? [{ ...PLUGIN, ...(overrides.plugin as object) }],
          });
        }
        if (args.kind === 'plugin' && args.action === 'install') {
          if (failInstall)
            return Promise.reject(
              new Error('plugin name already exists; pass overwrite=true explicitly to replace it')
            );
          return Promise.resolve({
            name: 'fresh',
            version: '0.1.0',
            path: 'fresh',
            permissions: { scopes: [], network: '', fs: '' },
            contains_summary: { skills: 1, hooks: 0, mcp: false },
          });
        }
        if (args.kind === 'plugin' && args.action === 'uninstall') {
          return Promise.resolve({ name: args.name, uninstalled: true, path: args.name });
        }
        return Promise.resolve({});
      case 'set_plugin_approval':
        if (failApproval) return Promise.reject(new Error('user operations only'));
        return Promise.resolve({ ...RESULT, name: args.name, approved: args.approved });
      default:
        return Promise.resolve({});
    }
  };
}

function renderBlock(impl: ReturnType<typeof backend>) {
  callCapabilityMock.mockImplementation(impl);
  render(<PluginsBlock />);
}

const toastTexts = () => useUIStore.getState().toasts.map((t) => t.message);

// Confirmations (overwrite / delete / revoke) answer through the shared
// confirmDialog stub (defaults to confirmed)
const confirmMock = stubConfirm(true);

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  uploadFileMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('settings page plugin block (roster)', () => {
  it('mounts with list_plugins and renders name/version/description/approval chip/permission list; no getApi()', async () => {
    renderBlock(backend());
    await waitFor(() => expect(screen.getByText('example v0.1.0')).toBeTruthy());
    expect(screen.getByText('最小插件示例')).toBeTruthy();
    expect(screen.getByText('未批准')).toBeTruthy();
    expect(screen.getByText(/技能 2 · 钩子 1 · MCP 配置/)).toBeTruthy();
    expect(screen.getByText(/请求权限：notes\.write/)).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
      kind: 'plugin',
      action: 'list',
    });
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('an empty list shows placement guidance', async () => {
    renderBlock(backend({ items: [] }));
    await waitFor(() => expect(screen.getByText(/还没有发现插件/)).toBeTruthy());
  });

  it('on load failure shows only the block-level retry hint', async () => {
    renderBlock(backend({}, true));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
  });

  it('the approval switch on an unapproved plugin → set_plugin_approval granularity bundle; the toast mentions pending MCP approval', async () => {
    renderBlock(backend());
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '整包批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('switch', { name: '整包批准 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'bundle',
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('外接 MCP') && m.includes('已批准插件'))).toBe(
        true
      )
    );
  });

  it('approved entries show the revoke switch → approved:false; the toast says it was removed', async () => {
    renderBlock(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '撤销批准 example' })).toBeTruthy()
    );
    expect(screen.getByText('已批准（整包）')).toBeTruthy();
    fireEvent.click(screen.getByRole('switch', { name: '撤销批准 example' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
        granularity: 'bundle',
      })
    );
    await waitFor(() => expect(toastTexts().some((m) => m.includes('已撤销插件'))).toBe(true));
  });

  it('approval failure fires an error toast (copy includes the failure reason, no bare error code)', async () => {
    renderBlock(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '整包批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('switch', { name: '整包批准 example' }));
    await waitFor(() => expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true));
  });
});

describe('settings page plugin custom per-item approval', () => {
  it('expanding the row shows skill/hook/MCP detail checkboxes; at least one must be checked to submit', async () => {
    renderBlock(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    expect(screen.getByRole('checkbox', { name: 'daily-note' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'weekly-review' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'note.created' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /example-search/ })).toBeTruthy();
    const submit = screen.getByRole('button', { name: '自定义批准' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it('submitting after checking → granularity item + the checked names; success toast and refresh', async () => {
    renderBlock(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'note.created' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'item',
        skills: ['daily-note'],
        hooks: ['hooks/on-note-created.json'],
        mcp: [],
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已批准插件') && m.includes('外接 MCP'))).toBe(
        true
      )
    );
  });

  it('approved (per-item) entries reopen pre-checked; resubmitting idempotently reinstalls', async () => {
    renderBlock(
      backend({
        plugin: {
          approved: true,
          granularity: 'item',
          skills: [
            { name: 'daily-note', approved: true },
            { name: 'weekly-review', approved: false },
          ],
          hooks: [
            {
              path: 'hooks/on-note-created.json',
              on: 'note.created',
              enabled: true,
              approved: true,
            },
          ],
        },
      })
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    expect((screen.getByRole('checkbox', { name: 'daily-note' }) as HTMLInputElement).checked).toBe(
      true
    );
    expect(
      (screen.getByRole('checkbox', { name: 'weekly-review' }) as HTMLInputElement).checked
    ).toBe(false);
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: true,
        granularity: 'item',
        skills: [],
        hooks: ['hooks/on-note-created.json'],
        mcp: [],
      })
    );
  });

  it('per-item approval failure fires an error toast and keeps the checkbox panel open', async () => {
    renderBlock(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() => expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true));
  });
});

describe('settings page plugin revoke reclaims MCP', () => {
  it('revoking shows a confirm listing the MCP ids with "registered and unapproved tools" before submitting', async () => {
    renderBlock(
      backend({
        plugin: {
          approved: true,
          granularity: 'bundle',
          mcp: [{ id: 'example-search', approved: true, registered: true, tools_approved: [] }],
        },
      })
    );
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('switch', { name: '撤销批准 example' }));
    const request = confirmMock.mock.calls[0]?.[0] as { message?: string } | undefined;
    expect(String(request?.message)).toContain('example-search');
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
        granularity: 'bundle',
      })
    );
  });

  it('cancelling the confirm sends no revoke request', async () => {
    confirmMock.mockResolvedValue(false);
    renderBlock(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('switch', { name: '撤销批准 example' }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'set_plugin_approval',
      expect.objectContaining({ approved: false })
    );
  });

  it('the revoke response discloses reclaim results: reclaimed ids listed, skipped ones with reasons', async () => {
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, args: Record<string, unknown>) => {
        if (name === 'extension' && args.action === 'list') {
          return Promise.resolve({ items: [{ ...PLUGIN, approved: true, granularity: 'bundle' }] });
        }
        if (name === 'set_plugin_approval') {
          return Promise.resolve({
            ...RESULT,
            name: args.name,
            approved: false,
            mcp_reclaimed: ['example-search'],
            mcp_reclaim_skipped: [{ id: 'manual-srv', reason: 'MCP 工具已批准，已保留' }],
          });
        }
        return Promise.resolve({});
      }
    );
    render(<PluginsBlock />);
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('switch', { name: '撤销批准 example' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已同步移除其外接 MCP：example-search'))).toBe(
        true
      )
    );
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.includes('未回收：manual-srv（MCP 工具已批准，已保留）'))
      ).toBe(true)
    );
  });

  it('when the per-item response carries mcp_reclaimed, the approval toast also discloses the removed MCPs', async () => {
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, args: Record<string, unknown>) => {
        if (name === 'extension' && args.action === 'list') {
          return Promise.resolve({ items: [{ ...PLUGIN }] });
        }
        if (name === 'set_plugin_approval') {
          return Promise.resolve({
            ...RESULT,
            name: args.name,
            approved: true,
            mcp_reclaimed: ['example-search'],
          });
        }
        return Promise.resolve({});
      }
    );
    render(<PluginsBlock />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '修改分项 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '修改分项 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已移除取消勾选的 MCP：example-search'))).toBe(
        true
      )
    );
  });
});

describe('settings page plugin install/delete (dialog)', () => {
  it('choosing a zip in the dialog and installing: uploadFile transports first then install_plugin{zip_path}; the toast includes the plugin name and the list refreshes', async () => {
    uploadFileMock.mockResolvedValue({
      file_path: 'C:/ws/imports/example.zip',
      filename: 'example.zip',
      size: 12,
    });
    renderBlock(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    const dialog = screen.getByRole('dialog');
    const file = new File(['PK'], 'example.zip');
    fireEvent.change(within(dialog).getByLabelText('选择 zip 安装包'), {
      target: { files: [file] },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() => expect(uploadFileMock).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
        kind: 'plugin',
        action: 'install',
        zip_path: 'C:/ws/imports/example.zip',
        overwrite: false,
      })
    );
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.includes('已安装插件「fresh」') && m.includes('尚未批准'))
      ).toBe(true)
    );
    const listCalls = callCapabilityMock.mock.calls.filter(
      (c) => c[1] === 'extension' && (c[2] as { action?: string })?.action === 'list'
    );
    expect(listCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('pasting a directory path and installing: install_plugin{source_dir}, no upload involved', async () => {
    renderBlock(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('插件目录路径'), {
      target: { value: 'C:/plugins-src/example' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
        kind: 'plugin',
        action: 'install',
        source_dir: 'C:/plugins-src/example',
        overwrite: false,
      })
    );
    expect(uploadFileMock).not.toHaveBeenCalled();
  });

  it('the install submit is disabled with neither a zip nor a path', async () => {
    renderBlock(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    const dialog = screen.getByRole('dialog');
    const submit = within(dialog).getByRole('button', { name: '安装插件' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });

  it('install failure fires an error toast with the backend-readable message', async () => {
    renderBlock(backend({}, false, false, true));
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(
        toastTexts().some(
          (m) => m.startsWith('安装失败：') && m.includes('plugin name already exists')
        )
      ).toBe(true)
    );
  });

  it('checking "overwrite same-name plugin" confirms before submit; cancelling sends nothing, confirming resends with overwrite:true', async () => {
    confirmMock.mockResolvedValue(false);
    renderBlock(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    let dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByLabelText('覆盖同名插件'));
    fireEvent.change(within(dialog).getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'install_plugin',
      expect.anything()
    );
    // The dialog stays open (the confirm was declined); confirm again with overwrite allowed
    confirmMock.mockResolvedValue(true);
    dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
        kind: 'plugin',
        action: 'install',
        source_dir: 'C:/x',
        overwrite: true,
      })
    );
  });

  it('busy while the install request is pending: the submit is disabled and double click sends once', async () => {
    let resolveInstall!: (v: unknown) => void;
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, args: Record<string, unknown>) => {
        if (name === 'extension' && args.kind === 'plugin' && args.action === 'list') {
          return Promise.resolve({ items: [{ ...PLUGIN }] });
        }
        if (name === 'extension' && args.action === 'install') {
          return new Promise((resolve) => {
            resolveInstall = resolve;
          });
        }
        return Promise.resolve({});
      }
    );
    render(<PluginsBlock />);
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    const dialog = screen.getByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(
        (within(dialog).getByRole('button', { name: '安装插件' }) as HTMLButtonElement).disabled
      ).toBe(true)
    );
    fireEvent.click(within(dialog).getByRole('button', { name: '安装插件' })); // disabled: no second request
    const installCalls = callCapabilityMock.mock.calls.filter(
      (c) => c[1] === 'extension' && (c[2] as { action?: string })?.action === 'install'
    );
    expect(installCalls).toHaveLength(1);
    resolveInstall({
      name: 'fresh',
      version: '0.1.0',
      path: 'fresh',
      permissions: { scopes: [], network: '', fs: '' },
      contains_summary: { skills: 0, hooks: 0, mcp: false },
    });
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已安装插件「fresh」'))).toBe(true)
    );
  });

  it('unapproved rows have "delete": confirm warns it is irreversible, then uninstall_plugin + toast', async () => {
    renderBlock(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '删除插件 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '删除插件 example' }));
    const delRequest = confirmMock.mock.calls[0]?.[0] as { message?: string } | undefined;
    expect(String(delRequest?.message)).toContain('不可恢复');
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'extension', {
        kind: 'plugin',
        action: 'uninstall',
        name: 'example',
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已删除插件「example」'))).toBe(true)
    );
  });

  it('approved plugins show no "delete" button (revoke first)', async () => {
    renderBlock(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('switch', { name: '撤销批准 example' })).toBeTruthy()
    );
    expect(screen.queryByRole('button', { name: '删除插件 example' })).toBeNull();
  });
});
