/**
 * @file themeToggle
 * @description Theme single-source tests at the useTheme hook level: the only
 * write path is settings.set_theme (including system); on failure the selection
 * and visuals stay unchanged. (The former topbar toggle cases were retired with
 * the topbar theme button.)
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { useTheme, type Theme } from '@/hooks/useTheme';
import { useUIStore } from '@/stores/uiStore';
import { applyTheme } from '@/shell/themeBridge';

beforeAll(() => {
  // jsdom gap: themeBridge reads the system light/dark preference
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  window.localStorage.clear(); // persist rehydration is not part of the assertions
  useUIStore.setState({ theme: 'light', toasts: [] });
  applyTheme('light');
});

describe('theme single source of truth (phase-06)', () => {
  it('changeTheme("system") also writes the backend; the selection and visuals follow on success', async () => {
    function Harness({ next }: { next: Theme }) {
      const { changeTheme } = useTheme();
      return (
        <button type="button" onClick={() => void changeTheme(next)}>
          go
        </button>
      );
    }
    render(
      <MemoryRouter>
        <Harness next="system" />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: 'go' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_theme', {
        theme: 'system',
      })
    );
    await waitFor(() => expect(useUIStore.getState().theme).toBe('system'));
    // system resolves to the current system preference (jsdom mock = light); data-theme is never left empty
    expect(document.documentElement.dataset.theme).toBe('light');
  });
});

describe('changeFontScale (F-1 fix: font_scale single write path via set_theme)', () => {
  it('after persist set_theme({font_scale}) succeeds, updates the store and applies the CSS variable', async () => {
    function Harness() {
      const { changeFontScale } = useTheme();
      return (
        <button type="button" onClick={() => void changeFontScale(1.2)}>
          go
        </button>
      );
    }
    render(
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: 'go' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_theme', {
        font_scale: 1.2,
      })
    );
    await waitFor(() => expect(useUIStore.getState().fontScale).toBe(1.2));
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1.2');
  });

  it('rethrows on save failure; the store and CSS variable keep their original values', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend service not started or unreachable'));
    useUIStore.setState({ fontScale: 1 });
    document.documentElement.style.setProperty('--font-scale', '1');

    function Harness() {
      const { changeFontScale } = useTheme();
      return (
        <button type="button" onClick={() => changeFontScale(1.3).catch(() => {})}>
          go
        </button>
      );
    }
    render(
      <MemoryRouter>
        <Harness />
      </MemoryRouter>
    );
    fireEvent.click(screen.getByRole('button', { name: 'go' }));

    await waitFor(() => expect(callCapabilityMock).toHaveBeenCalled());
    expect(useUIStore.getState().fontScale).toBe(1);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1');
  });
});
