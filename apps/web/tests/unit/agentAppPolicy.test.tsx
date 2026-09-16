/**
 * @file agentAppPolicy
 * @description Settings page Agent in-app capability allow/deny list unit
 * tests (phase-19): reading/saving the allow/deny lists goes through
 * settings.get_setting/set_setting, and an empty allow list / URL shapes /
 * values containing ".." send no request.
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

import { AppPolicyBlock } from '@/components/settings/agent/AppPolicyBlock';
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
      <AppPolicyBlock />
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
    expect((screen.getByLabelText(label) as HTMLTextAreaElement).value).toBe(expected)
  );
}

beforeAll(() => {
  initI18n();
});

describe('in-app capability allow/deny lists (phase-19)', () => {
  it('reads the defaults on mount: allow * / deny empty', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');
    await waitDraft('应用内能力拒绝名单', '');
  });

  it('saving an edited allow list writes agent.app.allowed (array)', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__create_note\ngraph__search' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.app.allowed',
        value: ['notes__create_note', 'graph__search'],
      })
    );
  });

  it('saving an edited deny list writes agent.app.denied', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力拒绝名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__delete_note\ngraph__*' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.app.denied',
        value: ['notes__delete_note', 'graph__*'],
      })
    );
  });

  it('clearing the allow list warns via toast without a request', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' })
    );
  });

  it('the mcp__* prefix can be saved (phase-31: external MCP also goes through the app dimension)', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'mcp__*' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.app.allowed',
        value: ['mcp__*'],
      })
    );
  });

  it('URL-shaped values are rejected without a request', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'https://github.com' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' })
    );
  });

  it('values containing ".." are rejected without a request', async () => {
    renderSection();
    await waitDraft('应用内能力允许名单', '*');

    const box = screen.getByLabelText('应用内能力允许名单') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'notes__../evil' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.app.allowed' })
    );
  });
});
