/**
 * @file themeToggle
 * @description Phase-06 theme single-source tests: even when the store and
 * the DOM drift, one click on the topbar switches the theme; the only write
 * path is settings.set_theme (including system); on failure the selection is
 * unchanged.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { Topbar } from '@/shell/Topbar';
import { useTheme } from '@/hooks/useTheme';
import { useUIStore, type Theme } from '@/stores/uiStore';
import { applyTheme } from '@/shell/themeBridge';
import { initI18n } from '@/i18n';

beforeAll(() => {
  // jsdom gap: Topbar / themeBridge read the system light/dark preference
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
  // Topbar copy and pageMeta titles go through i18n; the kernel must be ready (default zh-CN)
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  window.localStorage.clear(); // persist rehydration is not part of the assertions
  useUIStore.setState({ theme: 'light', toasts: [] });
  applyTheme('light');
});

function renderTopbar() {
  return render(
    <MemoryRouter>
      <Topbar />
    </MemoryRouter>
  );
}

describe('theme single source of truth (phase-06)', () => {
  it('when the store says light but the DOM is dark (historical dual-source drift), one topbar click switches to light and persists', async () => {
    applyTheme('dark'); // the screen shows dark
    useUIStore.setState({ theme: 'light' }); // the store still says light → two clicks before the fix

    renderTopbar();
    fireEvent.click(screen.getByRole('button', { name: '切换主题' }));

    // Direction follows what is visible (the DOM): emit light, not what the store thinks (dark)
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_theme', {
        theme: 'light',
      })
    );
    // after persistence succeeds the selection matches the visuals in a single click
    await waitFor(() => expect(useUIStore.getState().theme).toBe('light'));
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('changeTheme("system") also writes the backend; the selection and visuals follow on success', async () => {
    // The topbar only toggles light↔dark; the system entry is the settings page / same changeTheme (harness tests it directly)
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

  it('keeps the original selection and shows a toast when set_theme fails, without pretending success', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend service not started or unreachable'));
    applyTheme('dark');
    useUIStore.setState({ theme: 'dark' });

    renderTopbar();
    fireEvent.click(screen.getByRole('button', { name: '切换主题' }));

    await waitFor(() => {
      const last = useUIStore.getState().toasts.at(-1);
      expect(last?.type).toBe('error');
      expect(last?.message).toContain('主题切换失败');
    });
    expect(useUIStore.getState().theme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark'); // visuals unchanged too
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
