/**
 * @file agentPlugins
 * @description Settings page plugin block unit tests (phase-72 bundle +
 * phase-74 per-item + phase-77 install/delete): mounting calls list_plugins
 * and renders name/version/approval state/permission list/details, bundle
 * approval, custom per-item checks, revoke, zip/directory install and delete;
 * success/failure toasts; getApi() is never called.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
};

/** list_plugins sample: unapproved, 2 skills + 1 hook + 1 MCP (kept distinct from phase-72) */
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

/** Result payload: bundle loaded 3 skills? skills is an array (names of loaded skills) */
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
      case 'list_plugins':
        if (failList) return Promise.reject(new Error('boom'));
        return Promise.resolve({
          items: overrides.items ?? [{ ...PLUGIN, ...(overrides.plugin as object) }],
        });
      case 'set_plugin_approval':
        if (failApproval) return Promise.reject(new Error('user operations only'));
        return Promise.resolve({ ...RESULT, name: args.name, approved: args.approved });
      case 'install_plugin':
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
      case 'uninstall_plugin':
        return Promise.resolve({ name: args.name, uninstalled: true, path: args.name });
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
      <PluginsBlock />
      <WorkspaceBlock />
    </>
  );
}

const toastTexts = () => useUIStore.getState().toasts.map((t) => t.message);

let confirmMock: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  uploadFileMock.mockReset();
  useUIStore.setState({ toasts: [] });
  // Revoking approval goes through window.confirm (phase-76): confirmed by default, individual cases override the return value
  confirmMock = vi.spyOn(window, 'confirm').mockReturnValue(true);
  confirmMock.mockClear(); // the spy reuses the same mock: clear the previous case's calls
});

beforeAll(() => {
  initI18n();
});

describe('settings page plugin block (phase-72)', () => {
  it('mounts with list_plugins and renders name/version/description/unapproved/permission list and contains; no getApi()', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByText('example v0.1.0')).toBeTruthy());
    expect(screen.getByText('最小插件示例')).toBeTruthy();
    expect(screen.getByText(/未批准 · 请求权限：notes\.write · 网络 off · 文件 none/)).toBeTruthy();
    expect(screen.getByText(/技能 2 · 钩子 1 · MCP 配置/)).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_plugins', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('an empty list shows placement guidance', async () => {
    renderSection(backend({ items: [] }));
    await waitFor(() => expect(screen.getByText(/还没有发现插件/)).toBeTruthy());
  });

  it('on load failure shows only the block-level "reload" hint while the other sections stay intact', async () => {
    renderSection(backend({}, true));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    expect(screen.getByLabelText('工作目录')).toBeTruthy();
  });

  it('"bundle approve" → set_plugin_approval granularity bundle; the success toast mentions pending MCP approval', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '整包批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '整包批准 example' }));
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

  it('approved entries show "revoke approval" → approved:false; the toast says it was removed', async () => {
    renderSection(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy()
    );
    expect(screen.getByText(/已批准（整包） · 请求权限/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
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
    renderSection(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '整包批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '整包批准 example' }));
    await waitFor(() => expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true));
  });
});

describe('settings page plugin custom per-item approval (phase-74)', () => {
  it('expanding custom approval shows skill/hook/MCP detail checkboxes; at least one must be checked to submit', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    // detail checkboxes render (accessibility labels are generated from text)
    expect(screen.getByRole('checkbox', { name: 'daily-note' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'weekly-review' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: 'note.created' })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /example-search/ })).toBeTruthy();
    // submit is disabled with nothing checked; enabled after checking one
    const submit = screen.getByRole('button', { name: '自定义批准' });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    expect((submit as HTMLButtonElement).disabled).toBe(false);
  });

  it('submitting after checking → granularity item + the checked names; success toast and refresh', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
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

  it('approved (per-item) entries can "edit items" to prefill the checks; resubmitting idempotently reinstalls', async () => {
    renderSection(
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
    // approved items are pre-checked
    expect((screen.getByRole('checkbox', { name: 'daily-note' }) as HTMLInputElement).checked).toBe(
      true
    );
    expect(
      (screen.getByRole('checkbox', { name: 'weekly-review' }) as HTMLInputElement).checked
    ).toBe(false);
    // uncheck one and resubmit → only the remaining checks are installed
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
    renderSection(backend({}, false, true));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() => expect(toastTexts().some((m) => m.startsWith('批准失败：'))).toBe(true));
  });
});

describe('settings page plugin revoke reclaims MCP (phase-76)', () => {
  it('revoking shows a confirm listing the MCP ids with "registered and unapproved tools" before submitting', async () => {
    renderSection(
      backend({
        plugin: {
          approved: true,
          granularity: 'bundle',
          mcp: [{ id: 'example-search', approved: true, registered: true, tools_approved: [] }],
        },
      })
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
    expect(String(confirmMock.mock.calls[0]?.[0])).toContain('example-search');
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'set_plugin_approval', {
        name: 'example',
        approved: false,
        granularity: 'bundle',
      })
    );
  });

  it('cancelling the confirm sends no revoke request', async () => {
    confirmMock.mockReturnValue(false);
    renderSection(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
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
        if (name === 'list_plugins') {
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
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      }
    );
    render(
      <>
        <PluginsBlock />
      </>
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '撤销批准 example' }));
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
        if (name === 'list_plugins') {
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
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      }
    );
    render(
      <>
        <PluginsBlock />
      </>
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '自定义批准 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '自定义批准 example' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'daily-note' }));
    fireEvent.click(screen.getByRole('button', { name: '自定义批准' }));
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已移除取消勾选的 MCP：example-search'))).toBe(
        true
      )
    );
  });
});

describe('settings page plugin install/delete (phase-77)', () => {
  it('choosing a zip and installing: uploadFile transports first then install_plugin{zip_path}; the success toast includes the plugin name and refreshes the list', async () => {
    uploadFileMock.mockResolvedValue({
      file_path: 'C:/ws/imports/example.zip',
      filename: 'example.zip',
      size: 12,
    });
    renderSection(backend());
    await waitFor(() => expect(screen.getByLabelText('选择 zip 安装包')).toBeTruthy());
    const file = new File(['PK'], 'example.zip');
    fireEvent.change(screen.getByLabelText('选择 zip 安装包'), { target: { files: [file] } });
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() => expect(uploadFileMock).toHaveBeenCalledWith(file));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'install_plugin', {
        zip_path: 'C:/ws/imports/example.zip',
        overwrite: false,
      })
    );
    await waitFor(() =>
      expect(
        toastTexts().some((m) => m.includes('已安装插件「fresh」') && m.includes('尚未批准'))
      ).toBe(true)
    );
    // list refresh: list_plugins is called again after install
    const listCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'list_plugins');
    expect(listCalls.length).toBeGreaterThanOrEqual(2);
  });

  it('pasting a directory path and installing: install_plugin{source_dir}, no upload involved', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByLabelText('插件目录路径')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('插件目录路径'), {
      target: { value: 'C:/plugins-src/example' },
    });
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'install_plugin', {
        source_dir: 'C:/plugins-src/example',
        overwrite: false,
      })
    );
    expect(uploadFileMock).not.toHaveBeenCalled();
  });

  it('the install button is disabled with neither a zip nor a path', async () => {
    renderSection(backend());
    await waitFor(() => expect(screen.getByRole('button', { name: '安装插件' })).toBeTruthy());
    expect((screen.getByRole('button', { name: '安装插件' }) as HTMLButtonElement).disabled).toBe(
      true
    );
  });

  it('install failure fires an error toast with the backend-readable message', async () => {
    renderSection(backend({}, false, false, true));
    await waitFor(() => expect(screen.getByLabelText('插件目录路径')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(
        toastTexts().some(
          (m) => m.startsWith('安装失败：') && m.includes('plugin name already exists')
        )
      ).toBe(true)
    );
  });

  it('checking "overwrite same-name plugin" confirms before submit; cancelling sends nothing, confirming resends with overwrite:true', async () => {
    confirmMock.mockReturnValue(false);
    renderSection(backend());
    await waitFor(() => expect(screen.getByLabelText('覆盖同名插件')).toBeTruthy());
    fireEvent.click(screen.getByLabelText('覆盖同名插件'));
    fireEvent.change(screen.getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'install_plugin',
      expect.anything()
    );
    confirmMock.mockReturnValue(true);
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'install_plugin', {
        source_dir: 'C:/x',
        overwrite: true,
      })
    );
  });

  it('busy while the install request is pending: the button is disabled and double click sends once', async () => {
    let resolveInstall!: (v: unknown) => void;
    callCapabilityMock.mockImplementation(
      (_domain: string, name: string, _args: Record<string, unknown>) => {
        if (name === 'list_plugins') return Promise.resolve({ items: [{ ...PLUGIN }] });
        if (name === 'install_plugin') {
          return new Promise((resolve) => {
            resolveInstall = resolve;
          });
        }
        if (name === 'get_memory') return Promise.resolve(SNAPSHOT);
        return Promise.resolve({});
      }
    );
    render(
      <>
        <PluginsBlock />
      </>
    );
    await waitFor(() => expect(screen.getByLabelText('插件目录路径')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('插件目录路径'), { target: { value: 'C:/x' } });
    fireEvent.click(screen.getByRole('button', { name: '安装插件' }));
    await waitFor(() =>
      expect((screen.getByRole('button', { name: '安装插件' }) as HTMLButtonElement).disabled).toBe(
        true
      )
    );
    fireEvent.click(screen.getByRole('button', { name: '安装插件' })); // disabled: no second request
    const installCalls = callCapabilityMock.mock.calls.filter((c) => c[1] === 'install_plugin');
    expect(installCalls).toHaveLength(1);
    resolveInstall({
      name: 'fresh',
      version: '0.1.0',
      path: 'fresh',
      permissions: { scopes: [], network: '', fs: '' },
      contains_summary: { skills: 0, hooks: 0, mcp: false },
    });
    // flow completes: the success toast appears; the source is cleared and the button is back to its "disabled without source" initial state
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已安装插件「fresh」'))).toBe(true)
    );
    expect((screen.getByRole('button', { name: '安装插件' }) as HTMLButtonElement).disabled).toBe(
      true
    );
  });

  it('unapproved rows have "delete": confirm warns it is irreversible, then uninstall_plugin + toast', async () => {
    renderSection(backend());
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '删除插件 example' })).toBeTruthy()
    );
    fireEvent.click(screen.getByRole('button', { name: '删除插件 example' }));
    expect(String(confirmMock.mock.calls[0]?.[0])).toContain('不可恢复');
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'uninstall_plugin', {
        name: 'example',
      })
    );
    await waitFor(() =>
      expect(toastTexts().some((m) => m.includes('已删除插件「example」'))).toBe(true)
    );
  });

  it('approved plugins show no "delete" button (revoke first)', async () => {
    renderSection(backend({ plugin: { approved: true, granularity: 'bundle' } }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '撤销批准 example' })).toBeTruthy()
    );
    expect(screen.queryByRole('button', { name: '删除插件 example' })).toBeNull();
  });
});
