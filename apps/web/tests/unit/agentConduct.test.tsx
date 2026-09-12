/**
 * @file agentConduct
 * @description Settings page general/per-agent conduct unit tests (phase-29):
 * the draft comes from settings.get_setting and saving goes to
 * settings.set_setting (agent.conduct / agent.guidelines);
 * settingsStore.updateSettings is no longer used (getApi is never called);
 * per-agent saving merges the current tab and an empty string deletes the key.
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

import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
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
  'agent.conduct': '回答简洁',
  'agent.guidelines': { orchestrator: '先确认再改代码' },
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
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
  render(<AgentSettingsSection />);
}

beforeEach(() => {
  Object.assign(SETTINGS, {
    'agent.style': '热心',
    'agent.conduct': '回答简洁',
    'agent.guidelines': { orchestrator: '先确认再改代码' },
    'agent.memory.retention_days': 90,
    'agent.rounds.max': 20,
    'agent.rounds.tool_max': 40,
    'agent.network.mode': 'whitelist',
    'agent.network.domains': ['github.com'],
    'agent.workspace.dir': 'workspace',
  });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('general conduct (phase-29)', () => {
  it('the draft after mount comes from get_setting (agent.conduct)', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;
    expect(box.value).toBe('回答简洁');
  });

  it('saving writes set_setting {key: agent.conduct} without calling getApi', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '回答简洁,不用 emoji' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.conduct',
        value: '回答简洁,不用 emoji',
      })
    );
    expect(getApiMock).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true)
    );
  });

  it('saving after clearing writes back an empty string', async () => {
    renderSection();
    const box = (await screen.findByLabelText('通用行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.conduct',
        value: '',
      })
    );
  });
});

describe('per-agent conduct (phase-29)', () => {
  it('the draft after mount comes from the matching persona key of get_setting (agent.guidelines)', async () => {
    renderSection();
    const box = (await screen.findByLabelText('Lucien 行为准则')) as HTMLTextAreaElement;
    expect(box.value).toBe('先确认再改代码');
  });

  it('saving merges the current tab persona id while keeping the other keys intact', async () => {
    renderSection();
    await waitFor(() =>
      expect((screen.getByLabelText('Lucien 行为准则') as HTMLTextAreaElement).value).toBe(
        '先确认再改代码'
      )
    );

    fireEvent.click(screen.getByRole('tab', { name: 'Iris' }));
    const box = screen.getByLabelText('Iris 行为准则') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '只读不改' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.guidelines',
        value: { orchestrator: '先确认再改代码', recon: '只读不改' },
      })
    );
  });

  it('saving an emptied draft deletes the key from the object', async () => {
    renderSection();
    const box = (await screen.findByLabelText('Lucien 行为准则')) as HTMLTextAreaElement;

    fireEvent.change(box, { target: { value: '' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.guidelines',
        value: {},
      })
    );
  });
});

describe('speaking style keeps working after the move (phase-29)', () => {
  it('switching the level saves to agent.style', async () => {
    renderSection();
    await screen.findByLabelText('通用行为准则'); // page ready

    fireEvent.click(screen.getByRole('button', { name: '全局说话风格' }));
    fireEvent.click(screen.getByRole('option', { name: '毒舌' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.style',
        value: '毒舌',
      })
    );
  });
});
