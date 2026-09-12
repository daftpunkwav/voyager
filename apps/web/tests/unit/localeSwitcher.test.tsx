/**
 * @file localeSwitcher
 * @description Settings-page appearance section: the locale switcher renders
 * three choices, writes through the single changeLocale path (set_setting),
 * and the already-i18n'd section strings follow the active language.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/bridge/stream', () => ({
  subscribe: vi.fn(() => () => {}),
}));

vi.mock('@/api/settings', () => ({
  getSettings: vi.fn(async () => []),
}));

vi.mock('@/api/llm', () => ({
  listProviders: vi.fn(async () => []),
}));

vi.mock('@/hooks/useGithub', () => ({
  useGithubAccounts: () => ({ data: [], refetch: vi.fn() }),
}));

vi.mock('@/api/auth', () => ({
  setGithubToken: vi.fn(),
  unbindGithub: vi.fn(),
}));
vi.mock('@/api/projects', () => ({
  exportProjects: vi.fn(async () => []),
}));
vi.mock('@/api/notes', () => ({
  listAllNotes: vi.fn(async () => []),
}));

import { SettingsPage } from '@/pages/settings/SettingsPage';
import { useUIStore } from '@/stores/uiStore';
import { initI18n, i18n } from '@/i18n';

function renderPage() {
  return render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  window.localStorage.clear();
  useUIStore.setState({ theme: 'system', locale: 'zh-CN', toasts: [] });
  document.documentElement.lang = 'zh-CN';
});

describe('settings page locale switcher (phase-03)', () => {
  it('appearance section renders the zh heading and three locale options (endonyms are not translated)', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: '外观' })).toBeInTheDocument();
    expect(screen.getByTestId('locale-card-zh-CN')).toHaveTextContent('简体中文');
    expect(screen.getByTestId('locale-card-en')).toHaveTextContent('English');
    expect(screen.getByTestId('locale-card-system')).toHaveTextContent('跟随系统');
    expect(screen.getByTestId('locale-card-zh-CN')).toHaveClass('active');
  });

  it('clicking English goes through the single write path set_setting and switches the active state on success', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('locale-card-en'));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'appearance.locale',
        value: 'en',
      })
    );
    await waitFor(() => expect(useUIStore.getState().locale).toBe('en'));
    expect(screen.getByTestId('locale-card-en')).toHaveClass('active');
    expect(document.documentElement.lang).toBe('en');
  });

  it('keeps the active state and shows a toast when saving fails', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend unreachable'));
    renderPage();
    fireEvent.click(await screen.findByTestId('locale-card-en'));
    await waitFor(() => {
      const last = useUIStore.getState().toasts.at(-1);
      expect(last?.type).toBe('error');
      expect(last?.message).toContain('语言保存失败');
    });
    expect(useUIStore.getState().locale).toBe('zh-CN');
    expect(screen.getByTestId('locale-card-zh-CN')).toHaveClass('active');
  });

  it('after switching to English, the already-i18n appearance copy follows the language', async () => {
    const { rerender } = renderPage();
    expect(await screen.findByRole('heading', { name: '外观' })).toBeInTheDocument();
    await act(async () => {
      await i18n.changeLanguage('en');
    });
    rerender(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    );
    expect(screen.getByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
    expect(screen.getByText('UI language')).toBeInTheDocument();
    expect(screen.getByTestId('locale-card-system')).toHaveTextContent('System');
    await act(async () => {
      await i18n.changeLanguage('zh-CN');
    });
  });
});
