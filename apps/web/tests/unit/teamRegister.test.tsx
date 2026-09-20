/**
 * @file teamRegister
 * @description TeamPage agent registration + emergency stop unit tests
 * (phase-07): payload shape (the untrimmed submit omits allowed_tools / the
 * whitelist is sent as an array), invalid names blocked on the frontend,
 * same-name overwrite confirm, and cancel_run stop with the chat thinking
 * state.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

// Keep the real ServiceError (the stop NOT_FOUND branch is decided by instanceof + code)
vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { TeamPage } from '@/pages/team/TeamPage';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

beforeAll(() => {
  // Team page copy goes through the team ns t(); assertions keep zh resource values, so the i18n kernel must be ready
  initI18n();
});

/** Stateful mock: simulates the backend registry / spawner; register and cancel both mutate in-memory state */
let definitions: Array<Record<string, unknown>> = [];
let running: Array<Record<string, unknown>> = [];

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
    case 'tools':
      return Promise.resolve([
        { name: 'read_file', description: 'read file' },
        { name: 'write_file', description: 'write file' },
      ]);
    case 'list_subagents':
      return Promise.resolve({ definitions, running });
    case 'register_subagent': {
      definitions = [
        ...definitions.filter((d) => d.name !== args.name),
        {
          name: args.name,
          mode: args.mode ?? 'react',
          description: args.description,
          persona: args.persona ?? '',
          allowed_tools: (args.allowed_tools as string[] | undefined) ?? null,
          max_rounds: (args.max_rounds as number | undefined) ?? null,
          max_tool_calls: (args.max_tool_calls as number | undefined) ?? null,
          network_mode: (args.network_mode as string | undefined) ?? '',
        },
      ];
      return Promise.resolve({
        name: args.name,
        mode: args.mode ?? 'react',
        allowed_tools: args.allowed_tools ?? null,
      });
    }
    case 'cancel_run':
      running = running.filter((r) => r.id !== args.id_or_name && r.name !== args.id_or_name);
      return Promise.resolve({ cancelled: [args.id_or_name] });
    default:
      return Promise.resolve({});
  }
}

beforeEach(() => {
  definitions = [];
  running = [
    { id: 'run-1', name: 'indexer', status: 'running', goal: 'build index', started_ts: 1 },
  ];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  window.localStorage.clear();
  useUIStore.setState({ toasts: [] });
  useChatStore.setState({ messages: [], question: null, thinking: false, connected: true });
});

/** phase-20 helper: a running instance with last_step */
function runningWith(last_step?: string) {
  return [
    {
      id: 'run-1',
      name: 'indexer',
      status: 'running',
      goal: 'build index',
      started_ts: 1,
      last_step,
    },
  ];
}

/** Render and wait for the register form to be ready (the persona heading is present while loading, so it is not a data-ready signal) */
async function renderPage() {
  render(<TeamPage />);
  await waitFor(() => expect(screen.getByLabelText('名称')).toBeTruthy());
}

function fillForm(name: string, description: string) {
  fireEvent.change(screen.getByLabelText('名称'), { target: { value: name } });
  fireEvent.change(screen.getByLabelText('描述'), { target: { value: description } });
}

describe('agent register form (phase-07)', () => {
  it('the untrimmed submit omits allowed_tools and the definition appears in the list after registering', async () => {
    await renderPage();
    fillForm('scout', 'read-only scout');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    // payload shape: exactly four fields, no allowed_tools key
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout',
        description: 'read-only scout',
        mode: 'react',
        persona: '',
      })
    );
    // definitions are refreshed after success and the definition appears on the page
    await waitFor(() => expect(screen.getByText('read-only scout')).toBeTruthy());
    expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true);
  });

  it('explicit whitelist: 0 items blocks submission; checking items submits the tool array', async () => {
    await renderPage();
    fillForm('scout', 'recon');
    fireEvent.click(screen.getByRole('radio', { name: '指定白名单' }));

    fireEvent.click(screen.getByRole('button', { name: '注册' }));
    expect(screen.getByText('指定白名单时至少勾选 1 项工具')).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'register_subagent',
      expect.anything()
    );

    fireEvent.click(screen.getByRole('checkbox', { name: 'read_file' }));
    fireEvent.click(screen.getByRole('button', { name: '注册' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'scout',
        description: 'recon',
        mode: 'react',
        persona: '',
        allowed_tools: ['read_file'],
      })
    );
  });

  it('an invalid name is blocked on the frontend without sending a register request', async () => {
    await renderPage();
    fillForm('Bad Name', 'invalid name');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByText(/名称须为小写/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'register_subagent',
      expect.anything()
    );
  });

  it('registering with rounds + network (phase-10): the request body carries the three new keys and the card shows the levels', async () => {
    await renderPage();
    fillForm('guard', 'gatekeeper');
    fireEvent.change(screen.getByLabelText('ReAct 轮数'), { target: { value: '12' } });
    fireEvent.change(screen.getByLabelText('工具轮数'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: '网络权限档位' }));
    fireEvent.click(screen.getByRole('option', { name: '白名单' }));
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'register_subagent', {
        name: 'guard',
        description: 'gatekeeper',
        mode: 'react',
        persona: '',
        max_rounds: 12,
        max_tool_calls: 30,
        network_mode: 'whitelist',
      })
    );
    // definitions are refreshed after registering; the card shows rounds and the network level
    await waitFor(() => expect(screen.getByText('gatekeeper')).toBeTruthy());
    expect(screen.getByText(/轮数:\s*12 \/ 30/)).toBeTruthy();
    expect(screen.getByText('网络:白名单')).toBeTruthy();
  });

  it('non-positive-integer rounds are blocked on the frontend without sending a register request', async () => {
    await renderPage();
    fillForm('bad_rounds', 'invalid rounds');
    fireEvent.change(screen.getByLabelText('ReAct 轮数'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByText(/ReAct 轮数须为正整数/)).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'register_subagent',
      expect.anything()
    );
  });

  it('an existing name shows an overwrite confirm first and submits only after confirming', async () => {
    definitions = [
      {
        name: 'scout',
        mode: 'react',
        description: 'old definition',
        persona: '',
        allowed_tools: null,
      },
    ];
    await renderPage();
    fillForm('scout', 'new definition');
    fireEvent.click(screen.getByRole('button', { name: '注册' }));

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'register_subagent',
      expect.anything()
    );

    fireEvent.click(screen.getByRole('button', { name: '覆盖' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith(
        'agent',
        'register_subagent',
        expect.objectContaining({ name: 'scout' })
      )
    );
  });
});

describe('instance current step (phase-20)', () => {
  it('shows "current: ..." when last_step exists', async () => {
    running = runningWith('listing dir');
    await renderPage();
    expect(screen.getByText(/当前:listing dir/)).toBeTruthy();
  });

  it('no "current:" line appears without last_step', async () => {
    running = runningWith('');
    await renderPage();
    expect(screen.queryByText(/当前:/)).toBeNull();
  });

  it('no "current:" line appears when the last_step field is missing', async () => {
    running = [
      { id: 'run-1', name: 'indexer', status: 'running', goal: 'build index', started_ts: 1 },
    ];
    await renderPage();
    expect(screen.queryByText(/当前:/)).toBeNull();
  });
});

describe('instance emergency stop (phase-07)', () => {
  it('stopping a running instance calls cancel_run(id) and removes it from the list immediately', async () => {
    await renderPage();
    expect(screen.getByText('indexer')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '急停' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', {
        id_or_name: 'run-1',
      })
    );
    await waitFor(() => expect(screen.queryByText('indexer')).toBeNull());
    expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true);
  });

  it('stopping the chat main instance clears the conversation thinking state, reports via toast, and injects no message into the conversation', async () => {
    useChatStore.setState({ thinking: true });
    running = [
      { id: 'chat', name: 'chat', status: 'running', goal: 'talk to the user', started_ts: 1 },
    ];
    await renderPage();

    fireEvent.click(screen.getByRole('button', { name: '急停' }));
    await waitFor(() => expect(useChatStore.getState().thinking).toBe(false));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'cancel_run', { id_or_name: 'chat' })
    );
    expect(useChatStore.getState().messages).toHaveLength(0);
    expect(useUIStore.getState().toasts.some((t) => t.message.includes('对话主实例'))).toBe(true);
  });
});
