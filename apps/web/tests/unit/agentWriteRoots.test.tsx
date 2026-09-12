/**
 * @file agentWriteRoots
 * @description Settings page Agent read/write extra directories unit tests
 * (phase-56): the mount draft is shown line by line; saving trims/strips
 * empty lines and writes the JSON array to agent.fs.write_roots; relative
 * paths / paths with ".." segments / blank input only warn without sending a
 * request.
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
  'agent.fs.write_roots': ['E:\\shared', '/srv/dropbox'],
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

beforeEach(() => {
  SETTINGS['agent.fs.write_roots'] = ['E:\\shared', '/srv/dropbox'];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  getApiMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

/** Wait for the get_setting draft to fill the textarea (mount is async) */
async function waitDraft(expected: string) {
  await waitFor(() =>
    expect((screen.getByLabelText('读写附加目录') as HTMLTextAreaElement).value).toBe(expected)
  );
}

beforeAll(() => {
  initI18n();
});

describe('read/write extra directories (phase-56)', () => {
  it('reads the draft on mount: array shown line by line', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('E:\\shared\n/srv/dropbox');
  });

  it('on edit+save, trims/strips empty lines and writes the JSON array to agent.fs.write_roots', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('E:\\shared\n/srv/dropbox');

    const box = screen.getByLabelText('读写附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: ' /tmp/a\nE:\\b \n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.fs.write_roots',
        value: ['/tmp/a', 'E:\\b'],
      })
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true)
    );
  });

  it('rejects relative paths: warning toast, no request', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('E:\\shared\n/srv/dropbox');

    const box = screen.getByLabelText('读写附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'docs\n/tmp/a' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.fs.write_roots' })
    );
  });

  it('rejects paths containing ".." segments: warning toast, no request', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('E:\\shared\n/srv/dropbox');

    const box = screen.getByLabelText('读写附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: 'E:\\a\\..\\b' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ key: 'agent.fs.write_roots' })
    );
  });

  it('blank-lines-only input saves as an empty array', async () => {
    render(<AgentSettingsSection />);
    await waitDraft('E:\\shared\n/srv/dropbox');

    const box = screen.getByLabelText('读写附加目录') as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '\n\n' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.fs.write_roots',
        value: [],
      })
    );
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'success')).toBe(true)
    );
  });
});
