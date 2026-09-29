/**
 * @file DynamicSettingsGroup
 * @description Behavior tests for the schema-driven settings group: prefix
 * filtering, number range validation before any request, int coercion, bool
 * and choice saves, and the secret row's has_value-only display.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import type { SettingSchemaItem } from '@/api/types';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({ callCapability: callCapabilityMock }));

import { DynamicSettingsGroup } from '@/components/settings/dynamic/DynamicSettingsGroup';

function item(overrides: Partial<SettingSchemaItem>): SettingSchemaItem {
  return {
    key: 'test.key',
    module: 'test',
    type: 'int',
    description: '',
    secret: false,
    choices: [],
    min: null,
    max: null,
    has_value: false,
    default: 0,
    value: 0,
    ...overrides,
  };
}

const SCHEMA: SettingSchemaItem[] = [
  item({ key: 'agent.execution.tool_deadline_s', module: 'agent', value: 90, min: 0, max: 3600 }),
  item({ key: 'agent.context.history_max', module: 'agent', value: 60, min: 2, max: 1000 }),
  item({
    key: 'agent.arbiter.mode',
    module: 'agent',
    type: 'choice',
    choices: ['queue', 'auto', 'guide'],
    value: 'queue',
  }),
  item({ key: 'agent.mcp.instructions', module: 'agent', type: 'bool', value: true }),
  item({ key: 'agent.llm.api_key', module: 'agent', type: 'str', secret: true, has_value: true }),
  // Excluded by default: dedicated UI elsewhere
  item({ key: 'agent.context.model_profiles', module: 'agent', type: 'json', value: {} }),
];

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  // Stateful backend: set_setting writes through to the schema rows so the
  // post-save reload (get_settings) returns the updated rows, like the real
  // store does.
  const rows = SCHEMA.map((row) => ({ ...row }));
  callCapabilityMock.mockImplementation((_d, name, args) => {
    if (name === 'set_setting') {
      const row = rows.find((r) => r.key === String(args.key));
      if (row) row.value = args.value;
      return Promise.resolve(args);
    }
    if (name === 'get_settings') return Promise.resolve(rows);
    return Promise.resolve([]);
  });
  useSettingsStore.setState({ settings: SCHEMA, isLoading: false, error: null });
  useUIStore.setState({ toasts: [] });
});

afterEach(() => {
  useUIStore.setState({ toasts: [] });
});

describe('DynamicSettingsGroup', () => {
  it('renders only the filtered slice (model_profiles excluded), secret shows has_value', () => {
    render(<DynamicSettingsGroup prefixes={['agent.']} />);
    expect(screen.getByLabelText('工具超时（秒）')).toBeInTheDocument();
    expect(screen.getByLabelText('历史上限（条）')).toBeInTheDocument();
    // Secret row: status text only, no editable control
    expect(screen.getByText('已配置')).toBeInTheDocument();
    expect(screen.queryByLabelText('agent.llm.api_key')).not.toBeInTheDocument();
    // Excluded key never renders
    expect(screen.queryByLabelText('model_profiles')).not.toBeInTheDocument();
  });

  it('saves an in-range int on blur; out-of-range warns without a request', async () => {
    render(<DynamicSettingsGroup prefixes={['agent.execution.']} />);
    const box = screen.getByLabelText('工具超时（秒）') as HTMLInputElement;
    expect(box.value).toBe('90');

    fireEvent.change(box, { target: { value: '120' } });
    fireEvent.blur(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.execution.tool_deadline_s',
        value: 120,
      })
    );

    // The post-save reload unmounts rows while isLoading, so re-query the
    // re-created input instead of reusing the detached node
    const reloaded = await screen.findByLabelText('工具超时（秒）');
    fireEvent.change(reloaded, { target: { value: '99999' } });
    fireEvent.blur(reloaded);
    await waitFor(() =>
      expect(useUIStore.getState().toasts.some((t) => t.type === 'warning')).toBe(true)
    );
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'settings',
      'set_setting',
      expect.objectContaining({ value: 99999 })
    );
  });

  it('bool rows save on toggle', async () => {
    render(<DynamicSettingsGroup prefixes={['agent.mcp.']} />);
    const box = screen.getByLabelText('MCP 使用说明注入') as HTMLInputElement;
    fireEvent.click(box);
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
        key: 'agent.mcp.instructions',
        value: false,
      })
    );
  });
});
