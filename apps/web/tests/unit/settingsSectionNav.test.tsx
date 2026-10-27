/**
 * @file settingsSectionNav
 * @description Settings-page section wiring: the grouped navigation switches
 * the panel, the default section is the appearance one and an unknown section
 * value in the query degrades to it.
 */

import { fireEvent, render, screen } from '@testing-library/react';
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
import { useSettingsStore } from '@/stores/settingsStore';
import { initI18n } from '@/i18n';

function renderAt(query = '') {
  return render(
    <MemoryRouter initialEntries={[`/settings${query}`]}>
      <SettingsPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  initI18n();
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  useSettingsStore.setState({ settings: null, isLoading: false, error: null });
});

describe('settings page section navigation', () => {
  it('shows the appearance section when the query carries no section', async () => {
    renderAt();
    expect(await screen.findByRole('heading', { name: '外观' })).toBeInTheDocument();
  });

  it('switches to the section the navigation entry selects', async () => {
    renderAt();
    const generalEntry = await screen.findByRole('button', { name: '常规' });
    fireEvent.click(generalEntry);
    expect(await screen.findByRole('heading', { name: '常规' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '外观' })).not.toBeInTheDocument();
    expect(generalEntry).toHaveClass('active');
  });

  it('degrades to the appearance section when the query carries an unknown section', async () => {
    renderAt('?section=bogus');
    expect(await screen.findByRole('heading', { name: '外观' })).toBeInTheDocument();
  });
});
