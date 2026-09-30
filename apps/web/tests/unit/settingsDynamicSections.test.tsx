/**
 * @file settingsDynamicSections
 * @description Settings-page section wiring for the schema-driven groups: the
 * llm section mounts a DynamicSettingsGroup over the llm module (sample
 * defaults surface without a hand-written block per key, composed keys stay
 * excluded), and the mcp section exposes the wire-timeout/refresh/instruction
 * prefix rows next to the server block.
 */

import { render, screen } from '@testing-library/react';
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

const SCHEMA = [
  {
    key: 'llm.temperature',
    module: 'llm',
    type: 'float',
    description: '',
    secret: false,
    choices: [],
    min: null,
    max: null,
    has_value: true,
    default: 0.7,
    value: 0.7,
  },
  {
    key: 'llm.request_timeout_s',
    module: 'llm',
    type: 'int',
    description: '',
    secret: false,
    choices: [],
    min: 5,
    max: 600,
    has_value: true,
    default: 120,
    value: 120,
  },
  // Composed per model in the LLM rail UI: must never duplicate as a row
  {
    key: 'llm.default_provider',
    module: 'llm',
    type: 'str',
    description: '',
    secret: false,
    choices: [],
    min: null,
    max: null,
    has_value: false,
    default: '',
    value: '',
  },
  {
    key: 'agent.mcp.wire_timeout_s',
    module: 'agent',
    type: 'int',
    description: '',
    secret: false,
    choices: [],
    min: 3,
    max: 300,
    has_value: true,
    default: 15,
    value: 15,
  },
  {
    key: 'agent.mcp.instructions',
    module: 'agent',
    type: 'bool',
    description: '',
    secret: false,
    choices: [],
    min: null,
    max: null,
    has_value: true,
    default: true,
    value: true,
  },
];

vi.mock('@/api/settings', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/settings')>()),
  getSettings: vi.fn(async () => SCHEMA),
}));

vi.mock('@/api/llm', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/api/llm')>()),
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

function renderAtSection(section: string) {
  return render(
    <MemoryRouter initialEntries={[`/settings?section=${section}`]}>
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

describe('settings page schema-driven sections', () => {
  it('the llm section mounts the llm-module dynamic group (sample defaults); composed keys stay excluded', async () => {
    renderAtSection('llm');
    expect(await screen.findByRole('heading', { name: '采样默认值' })).toBeInTheDocument();
    // llm-module rows render with their localized labels
    expect(screen.getByLabelText('采样温度')).toBeInTheDocument();
    expect(screen.getByLabelText('请求超时（秒）')).toBeInTheDocument();
    // default_provider has its dedicated rail UI in the same section: the
    // dynamic group must not duplicate it (last-segment fallback label)
    expect(screen.queryByLabelText('default_provider')).not.toBeInTheDocument();
  });

  it('the mcp section exposes the wire-timeout prefix rows alongside the server block', async () => {
    renderAtSection('mcp');
    expect(await screen.findByLabelText('MCP 连接超时（秒）')).toBeInTheDocument();
    expect(screen.getByLabelText('MCP 使用说明注入')).toBeInTheDocument();
    // The section heading is the mcp nav title, not a blank panel
    expect(screen.getByRole('heading', { name: '外接 MCP' })).toBeInTheDocument();
  });
});
