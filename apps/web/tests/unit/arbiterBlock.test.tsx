/**
 * @file arbiterBlock
 * @description Settings -> Agent arbiter-mode block (moved from the chat
 * topbar): read on mount, optimistic switch with a get_setting read-back,
 * rollback + toast on failure.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ArbiterBlock } from '@/components/settings/agent/ArbiterBlock';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

describe('ArbiterBlock', () => {
  it('reads the current mode and renders the localized options', async () => {
    callCapabilityMock.mockResolvedValue({ value: 'auto' });
    render(<ArbiterBlock />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('自动')
    );
  });

  it('switching goes through set_setting and reads back consistently', async () => {
    let current = 'queue';
    callCapabilityMock.mockImplementation(
      async (_d: string, name: string, args: Record<string, unknown>) => {
        if (name === 'get_setting') return { value: current };
        if (name === 'set_setting') {
          current = String(args.value);
          return { key: args.key, ok: true };
        }
        return {};
      }
    );
    render(<ArbiterBlock />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('排队')
    );
    fireEvent.click(screen.getByRole('button', { name: '仲裁模式' }));
    fireEvent.click(screen.getByRole('option', { name: '引导' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.arbiter.mode',
        value: 'guide',
      })
    );
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('引导')
    );
    const toasts = useUIStore.getState().toasts;
    expect(toasts.at(-1)?.type).toBe('success');
  });

  it('rolls back and toasts an error when the write fails', async () => {
    callCapabilityMock.mockImplementation(async (_d: string, name: string) => {
      if (name === 'get_setting') return { value: 'queue' };
      if (name === 'set_setting') throw new Error('backend down');
      return {};
    });
    render(<ArbiterBlock />);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('排队')
    );
    fireEvent.click(screen.getByRole('button', { name: '仲裁模式' }));
    fireEvent.click(screen.getByRole('option', { name: '自动' }));
    await waitFor(() => expect(useUIStore.getState().toasts.at(-1)?.type).toBe('error'));
    expect(screen.getByRole('button', { name: '仲裁模式' })).toHaveTextContent('排队');
  });
});
