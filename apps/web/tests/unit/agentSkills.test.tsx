/**
 * @file agentSkills
 * @description Settings page skill list unit tests (phase-11): list_skills
 * renders name+description, the empty-state hint, and failures only affect
 * this block without crashing the page; getApi() is never called.
 */

import { render, screen, waitFor } from '@testing-library/react';
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

/** Keyed settings store (same approach as agentSettingsLimits to avoid type mismatches failing other blocks) */
const SETTINGS: Record<string, unknown> = {
  'agent.style': '热心',
  'agent.memory.retention_days': 90,
  'agent.rounds.max': 20,
  'agent.rounds.tool_max': 40,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
  'agent.workspace.dir': 'workspace',
};

function backend(skills: unknown, failSkills = false) {
  return (_domain: string, name: string, args: Record<string, unknown>) => {
    switch (name) {
      case 'list_skills':
        return failSkills ? Promise.reject(new Error('boom')) : Promise.resolve(skills);
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
  render(<AgentSettingsSection />);
}

beforeEach(() => {
  callCapabilityMock.mockReset();
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

beforeAll(() => {
  initI18n();
});

describe('settings page skill list (phase-11)', () => {
  it('fetches via agent.list_skills on mount and renders name + description', async () => {
    renderSection(backend([{ name: 'explore-repo', description: '了解一个仓库的流程' }]));
    await waitFor(() => expect(screen.getByText('explore-repo')).toBeTruthy());
    expect(screen.getByText('了解一个仓库的流程')).toBeTruthy();
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'list_skills', {});
    expect(getApiMock).not.toHaveBeenCalled();
  });

  it('shows placement guidance for an empty list', async () => {
    renderSection(backend([]));
    await waitFor(() => expect(screen.getByText(/skills\/<名称>\//)).toBeTruthy());
  });

  it('on load failure shows only the block-level "reload" hint while the other sections stay intact', async () => {
    renderSection(backend([], true));
    await waitFor(() => expect(screen.getByText('读取失败请刷新。')).toBeTruthy());
    // Other sections on the page do not crash: the workspace-dir input still renders
    expect((screen.getByLabelText('工作目录') as HTMLInputElement).value).toBe('workspace');
  });
});
