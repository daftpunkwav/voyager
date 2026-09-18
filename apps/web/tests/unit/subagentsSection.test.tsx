/**
 * @file subagentsSection
 * @description Settings 子代理 section unit tests: roster rendering with the
 * 10-row cap and "show all" expander, search filtering, per-row enable toggle
 * (register_subagent with enabled flipped), delete (delete_subagent behind a
 * confirm), and the create/edit dialog (name locked when editing, payload
 * carries enabled, group select-all in the tool picker).
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { SubagentsSection } from '@/components/settings/subagents/SubagentsSection';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

let definitions: Array<Record<string, unknown>> = [];
let registered: Array<Record<string, unknown>> = [];
let deleted: string[] = [];

function makeDef(i: number): Record<string, unknown> {
  return {
    name: `agent_${i}`,
    mode: 'react',
    description: `def number ${i}`,
    persona: '',
    allowed_tools: null,
    max_rounds: null,
    max_tool_calls: null,
    network_mode: '',
    readonly: false,
    enabled: true,
  };
}

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'list_personas':
      return Promise.resolve([
        {
          key: 'orchestrator',
          display_name: 'Lucien',
          style: '',
          default_mode: 'react',
          tool_allow: null,
          system_prompt: '',
        },
      ]);
    case 'list_tools':
      return Promise.resolve([
        { name: 'read_file', description: 'read file', dimension: 'fs', write: false },
        { name: 'write_file', description: 'write file', dimension: 'fs', write: true },
        { name: 'notes__create_note', description: 'create note', dimension: 'app', write: true },
      ]);
    case 'list_subagents':
      return Promise.resolve({ definitions, running: [] });
    case 'register_subagent':
      registered.push(args);
      definitions = [
        ...definitions.filter((d) => d.name !== args.name),
        { ...(definitions.find((d) => d.name === args.name) ?? makeDef(0)), ...args },
      ];
      return Promise.resolve({ name: args.name });
    case 'delete_subagent':
      deleted.push(String(args.name));
      definitions = definitions.filter((d) => d.name !== args.name);
      return Promise.resolve({ deleted: args.name });
    default:
      return Promise.resolve({});
  }
}

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  definitions = [];
  registered = [];
  deleted = [];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
});

describe('settings subagents section (roster)', () => {
  it('renders definition rows with chips, description, an enable switch and a delete action', async () => {
    definitions = [
      { ...makeDef(1), name: 'scout', description: 'read-only scout', readonly: true },
    ];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    expect(screen.getByText('read-only scout')).toBeTruthy();
    expect(screen.getByText('只读')).toBeTruthy();
    expect(screen.getByText('全部工具')).toBeTruthy();
    expect(screen.getByRole('switch', { name: '启用或停用 scout' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '删除 scout' })).toBeTruthy();
  });

  it('caps the roster at 10 rows and expands to the full list on demand', async () => {
    definitions = Array.from({ length: 13 }, (_, i) => makeDef(i));
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('agent_0')).toBeTruthy());
    expect(screen.queryByText('agent_10')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '显示全部 3 个' }));
    await waitFor(() => expect(screen.getByText('agent_10')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '收起' }));
    await waitFor(() => expect(screen.queryByText('agent_10')).toBeNull());
  });

  it('search filters the roster by name and description', async () => {
    definitions = [
      { ...makeDef(1), name: 'scout', description: 'recon helper' },
      { ...makeDef(2), name: 'writer', description: 'drafts notes' },
    ];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('搜索子代理…'), { target: { value: 'drafts' } });
    await waitFor(() => expect(screen.queryByText('scout')).toBeNull());
    expect(screen.getByText('writer')).toBeTruthy();
  });

  it('toggling the enable switch re-registers the definition with enabled flipped', async () => {
    definitions = [{ ...makeDef(1), name: 'scout' }];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    fireEvent.click(screen.getByRole('switch', { name: '启用或停用 scout' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({ name: 'scout', enabled: false })
      )
    );
  });

  it('delete goes through a confirm dialog and hits delete_subagent', async () => {
    definitions = [{ ...makeDef(1), name: 'scout' }];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '删除 scout' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/删除「scout」/)).toBeTruthy();
    fireEvent.click(within(dialog).getByRole('button', { name: '删除' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'delete_subagent', {
        name: 'scout',
      })
    );
    expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true);
  });
});

describe('settings subagents section (create/edit dialog)', () => {
  it('creating: 新建 opens the dialog; a valid submit sends the full payload including enabled:true', async () => {
    definitions = [];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByRole('button', { name: '+ 新建' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '+ 新建' }));
    // The dialog opens after the lazy list_tools fetch resolves
    await waitFor(() => expect(screen.getByLabelText('名称')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'repo_scout' } });
    fireEvent.change(screen.getByLabelText('描述'), { target: { value: 'scans repos' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({
          name: 'repo_scout',
          description: 'scans repos',
          mode: 'react',
          persona: '',
          enabled: true,
          readonly: false,
        })
      )
    );
  });

  it('creating with a whitelist: the group select-all picks the whole category in one click', async () => {
    definitions = [];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByRole('button', { name: '+ 新建' })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '+ 新建' }));
    await waitFor(() => expect(screen.getByLabelText('名称')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('名称'), { target: { value: 'reader' } });
    fireEvent.change(screen.getByLabelText('描述'), { target: { value: 'reads stuff' } });
    fireEvent.click(screen.getByRole('radio', { name: '指定白名单' }));
    // The notes group select-all grants notes__create_note without touching it directly
    fireEvent.click(screen.getByRole('checkbox', { name: '全选或清空 笔记' }));
    expect(
      (screen.getByRole('checkbox', { name: 'notes__create_note' }) as HTMLInputElement).checked
    ).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({
          name: 'reader',
          allowed_tools: ['notes__create_note'],
        })
      )
    );
  });

  it('editing: clicking a row opens the dialog with the name locked; saving re-registers the same name', async () => {
    definitions = [
      {
        ...makeDef(1),
        name: 'scout',
        description: 'old description',
        allowed_tools: ['web_search'],
      },
    ];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '编辑 scout' }));
    await waitFor(() =>
      expect((screen.getByLabelText('名称') as HTMLInputElement).value).toBe('scout')
    );
    const nameInput = screen.getByLabelText('名称') as HTMLInputElement;
    expect(nameInput.disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({ name: 'scout', description: 'old description' })
      )
    );
  });

  it('the edit dialog exposes delete and hitting it removes the definition', async () => {
    definitions = [{ ...makeDef(1), name: 'scout' }];
    render(<SubagentsSection />);
    await waitFor(() => expect(screen.getByText('scout')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '编辑 scout' }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: '删除' }));
    // Two dialogs are stacked now (edit dialog + confirm): pick the confirm one by its message
    const confirmDialog = screen
      .getAllByRole('dialog')
      .find((d) => d.textContent?.includes('删除「scout」'));
    fireEvent.click(within(confirmDialog!).getByRole('button', { name: '删除' }));
    await waitFor(() => expect(deleted).toEqual(['scout']));
  });
});
