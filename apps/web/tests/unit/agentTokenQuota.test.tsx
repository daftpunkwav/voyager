/**
 * @file agentTokenQuota
 * @description Settings page Agent daily token quota unit tests (phase-61):
 * the mount reads the draft, saving writes agent.resource.daily_tokens,
 * out-of-range values are rejected without a request, and 0=unlimited is
 * valid.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, it, expect, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/client', () => ({ getApi: vi.fn() }));

import { TokenQuotaBlock } from '@/components/settings/agent/TokenQuotaBlock';
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
  'agent.resource.daily_tokens': 500000,
  'agent.network.mode': 'whitelist',
  'agent.network.domains': ['github.com'],
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
      <TokenQuotaBlock />
    </>
  );
}

beforeEach(() => {
  Object.assign(SETTINGS, { 'agent.resource.daily_tokens': 500000 });
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
});

/** Wait for the get_setting draft to fill the input (mount is async) */
async function waitDraft(expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText('Token 日配额') as HTMLInputElement).value).toBe(expected)
  );
}

beforeAll(() => {
  initI18n();
});

describe('daily token quota (phase-61)', () => {
  it('reads the draft on mount', async () => {
    renderSection();
    await waitDraft('500000');
  });

  it('saving writes agent.resource.daily_tokens as an integer', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '250000' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.resource.daily_tokens',
        value: 250000,
      })
    );
  });

  it('rejects values over the cap (10000000) without a request', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '10000001' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' })
    );
  });

  it('0 is valid (unlimited) and saves normally', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '0' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.resource.daily_tokens',
        value: 0,
      })
    );
  });

  it('rejects non-integers (negatives) without a request', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '-5' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' })
    );
  });

  it('rejects clearing the input (empty string) without a request — prevents silently storing 0=unlimited', async () => {
    renderSection();
    await waitDraft('500000');

    fireEvent.change(screen.getByLabelText('Token 日配额'), { target: { value: '' } });
    fireEvent.blur(screen.getByLabelText('Token 日配额'));
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.resource.daily_tokens' })
    );
  });
});
