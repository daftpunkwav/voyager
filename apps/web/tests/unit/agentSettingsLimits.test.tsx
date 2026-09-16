/**
 * @file agentSettingsLimits
 * @description Settings page Agent rounds/network/workspace unit tests
 * (phase-10): the get_setting mock branches strictly by key (the memory
 * section coexists on the page), changed values go to the correct settings
 * keys, and invalid rounds / URL-shaped domains / paths containing ".." send
 * no request.
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

import { useChatStore } from '@/stores/chatStore';
import { RoundsBlock } from '@/components/settings/agent/RoundsBlock';
import { NetworkBlock } from '@/components/settings/agent/NetworkBlock';
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

/** Keyed settings store; set_setting writes back and is reset between cases */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com', 'arxiv.org'],
  'agent.workspace.dir': 'workspace',
  'agent.app.allowed': ['*'],
  'agent.app.denied': [],
};

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'get_memory':
      return Promise.resolve(SNAPSHOT);
    case 'get_setting':
      return Promise.resolve({ value: SETTINGS[String(args.key)] });
    case 'set_setting':
      SETTINGS[String(args.key)] = args.value;
      return Promise.resolve({ value: args.value });
    default:
      return Promise.resolve({});
  }
}

function renderSection() {
  render(
    <>
      <RoundsBlock />
      <NetworkBlock />
      <WorkspaceBlock />
    </>
  );
}

beforeEach(() => {
  Object.assign(SETTINGS, {
    'agent.style': '热心',
    'agent.memory.retention_days': 90,
    'agent.rounds.max': 20,
    'agent.rounds.tool_max': 40,
    'agent.network.mode': 'whitelist',
    'agent.network.domains': ['github.com', 'arxiv.org'],
    'agent.workspace.dir': 'workspace',
    'agent.app.allowed': ['*'],
    'agent.app.denied': [],
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

/** Wait for the get_setting draft to fill the input (mount is async) */
async function waitDraft(label: string, expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText(label) as HTMLInputElement).value).toBe(expected)
  );
}

beforeAll(() => {
  initI18n();
});

describe('round limits (phase-10)', () => {
  it('reads the draft on mount; blur saves to agent.rounds.max', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    fireEvent.change(screen.getByLabelText('ReAct 轮数上限'), { target: { value: '25' } });
    fireEvent.blur(screen.getByLabelText('ReAct 轮数上限'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.rounds.max',
        value: 25,
      })
    );
  });

  it('out-of-range rounds warn via toast without a request', async () => {
    renderSection();
    await waitDraft('工具调用轮数上限', '40');

    fireEvent.change(screen.getByLabelText('工具调用轮数上限'), { target: { value: '999' } });
    fireEvent.blur(screen.getByLabelText('工具调用轮数上限'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.rounds.tool_max' })
    );
  });
});

describe('network permission (phase-10)', () => {
  it('switching the mode saves the backend enum value (off|whitelist|all)', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20'); // page ready

    fireEvent.click(screen.getByRole('button', { name: '网络权限模式' }));
    fireEvent.click(screen.getByRole('option', { name: '全开' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.network.mode',
        value: 'all',
      })
    );
  });

  it('whitelist domains one per line: saved as a JSON array after trim/stripping empty lines', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    const box = screen.getByLabelText('白名单域名') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'github.com\n pypi.org \n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.network.domains',
        value: ['github.com', 'pypi.org'],
      })
    );
  });

  it('full URL-shaped domains are rejected without a request', async () => {
    renderSection();
    await waitDraft('ReAct 轮数上限', '20');

    const box = screen.getByLabelText('白名单域名') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'https://github.com' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.network.domains' })
    );
  });
});

describe('workspace directory (phase-10, hot-switch)', () => {
  it('saving hot-switches through the switch endpoint after confirming', async () => {
    const confirmMock = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ workspace: 'ws2' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    try {
      renderSection();
      await waitDraft('工作目录', 'workspace');

      fireEvent.change(screen.getByLabelText('工作目录'), { target: { value: 'ws2' } });
      fireEvent.blur(screen.getByLabelText('工作目录'));
      await waitFor(() => expect(confirmMock).toHaveBeenCalled());
      await waitFor(() =>
        expect(fetchMock).toHaveBeenCalledWith(
          '/api/workspace/switch',
          expect.objectContaining({ method: 'POST' })
        )
      );
      const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body ?? '{}'));
      // The request carries the echo marker and it was stashed before the
      // POST, so this tab's useChatStream skips the "switched elsewhere" toast.
      expect(body.dir).toBe('ws2');
      expect(typeof body.marker).toBe('string');
      expect(body.marker).not.toBe('');
      expect(useChatStore.getState().workspaceSwitchMarker).toBe(body.marker);
      await waitFor(() =>
        expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true)
      );
    } finally {
      confirmMock.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('cancelling the confirm sends no switch request', async () => {
    const confirmMock = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    try {
      renderSection();
      await waitDraft('工作目录', 'workspace');

      fireEvent.change(screen.getByLabelText('工作目录'), { target: { value: 'ws2' } });
      fireEvent.blur(screen.getByLabelText('工作目录'));
      await waitFor(() => expect(confirmMock).toHaveBeenCalled());
      expect(fetchMock).not.toHaveBeenCalled();
    } finally {
      confirmMock.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it('paths containing ".." segments are rejected without a request', async () => {
    renderSection();
    await waitDraft('工作目录', 'workspace');

    fireEvent.change(screen.getByLabelText('工作目录'), { target: { value: '../evil' } });
    fireEvent.blur(screen.getByLabelText('工作目录'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.workspace.dir' })
    );
  });
});
