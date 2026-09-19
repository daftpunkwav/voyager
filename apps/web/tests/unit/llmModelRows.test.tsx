/**
 * @file llmModelRows
 * @description LLM settings model list: one row per model with inline
 * test / edit / delete actions and an enable switch, plus the shared edit
 * dialog reused in add mode. Provider-level default model is retired — an
 * untagged call resolves to the first enabled model (api/llm#firstEnabledModel).
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, setCalls } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  setCalls: [] as Array<{ key: string; value: unknown }>,
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { LlmProviderDetail } from '@/components/settings/llm/LlmProviderDetail';
import { firstEnabledModel } from '@/api/llm';
import type { LlmProvider } from '@/api/types';
import { initI18n } from '@/i18n';

const PROVIDER: LlmProvider = {
  id: 'p1',
  preset_id: '',
  display_name: 'MiniMax',
  base_url: 'https://api.minimaxi.com/v1',
  api_format: 'chat',
  models: ['m-a', 'm-b'],
  models_meta: {
    'm-a': { thinking: true, context_window: 1_000_000, enabled: false },
    'm-b': { image_input: true },
  },
  enabled: true,
  custom: false,
  has_api_key: true,
};

const setup = () => {
  const onPatch = vi.fn().mockResolvedValue(undefined);
  const onTestModel = vi.fn().mockResolvedValue({ ok: true, latency_ms: 120, model: 'm-a' });
  render(
    <LlmProviderDetail
      provider={PROVIDER}
      onPatch={onPatch}
      onSaveKey={vi.fn().mockResolvedValue(undefined)}
      onDelete={vi.fn()}
      onTestModel={onTestModel}
    />
  );
  return { onPatch, onTestModel };
};

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  setCalls.length = 0;
  callCapabilityMock.mockReset().mockImplementation((_d: string, name: string, payload?) => {
    if (name === 'get_setting') return Promise.resolve({ key: payload?.key, value: {} });
    if (name === 'set_setting') {
      setCalls.push({ key: payload?.key, value: payload?.value });
      return Promise.resolve({});
    }
    return Promise.resolve({});
  });
});

describe('firstEnabledModel', () => {
  it('skips disabled models and falls back to the first entry', () => {
    expect(firstEnabledModel(PROVIDER)).toBe('m-b');
    expect(firstEnabledModel({ ...PROVIDER, models_meta: {} })).toBe('m-a');
    expect(firstEnabledModel({ ...PROVIDER, models: [], models_meta: {} })).toBe('');
    expect(firstEnabledModel(null)).toBe('');
  });
});

/** Finds a button by its exact text inside a dialog; throws (failing the test
 *  with a clear message) when absent instead of a non-null assertion. */
function dialogButton(dialog: HTMLElement, text: string): HTMLButtonElement {
  const btn = [...dialog.querySelectorAll('button')].find((b) => b.textContent === text);
  if (!btn) throw new Error(`dialog button "${text}" not found`);
  return btn;
}

describe('LlmProviderDetail model rows', () => {
  it('renders one row per model with badges and the enabled switch state', () => {
    setup();
    expect(screen.getByText('m-a')).toBeTruthy();
    expect(screen.getByText('m-b')).toBeTruthy();
    expect(screen.getByText('1M')).toBeTruthy(); // context window badge
    // m-a is disabled, m-b enabled (model-row switches carry the model name)
    const switches = screen.getAllByRole('switch', { name: /启用或禁用 m-/ });
    expect(switches).toHaveLength(2);
    expect(switches[0].getAttribute('aria-checked')).toBe('false');
    expect(switches[1].getAttribute('aria-checked')).toBe('true');
  });

  it('toggling a model patches models_meta with the enabled flag', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getAllByRole('switch', { name: /启用或禁用 m-/ })[0]);
    await waitFor(() => expect(onPatch).toHaveBeenCalled());
    const patch = onPatch.mock.calls[0][0];
    expect(patch.models_meta['m-a'].enabled).toBe(true);
    expect(patch.models_meta['m-a'].thinking).toBe(true); // existing meta preserved
  });

  it('adds a model through the dialog: id + meta land in one patch, budgets mirror into model_profiles', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型' }));
    const dialog = await screen.findByRole('dialog', { name: '添加模型' });
    expect(dialog).toBeTruthy();
    fireEvent.change(screen.getByLabelText('模型 ID'), { target: { value: 'm-new' } });
    fireEvent.change(screen.getByLabelText('上下文窗口'), { target: { value: '900000' } });
    // the dialog's confirm button carries the add label (same text as the list header button)
    fireEvent.click(dialogButton(dialog, '+ 添加模型'));
    await waitFor(() => expect(onPatch).toHaveBeenCalled());
    const patch = onPatch.mock.calls[0][0];
    expect(patch.models).toEqual(['m-a', 'm-b', 'm-new']);
    expect(patch.models_meta['m-new'].context_window).toBe(900000);
    await waitFor(() => {
      const entry = setCalls.find((c) => c.key === 'agent.context.model_profiles');
      const profiles = entry?.value as Record<string, { window_tokens?: number }>;
      expect(profiles['m-new'].window_tokens).toBe(900000);
    });
  });

  it('duplicate model ids are rejected in add mode', async () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: '+ 添加模型' }));
    await screen.findByRole('dialog', { name: '添加模型' });
    fireEvent.change(screen.getByLabelText('模型 ID'), { target: { value: 'm-a' } });
    // confirm button is the dialog's primary action carrying the add label
    const dialog = screen.getByRole('dialog', { name: '添加模型' });
    fireEvent.click(dialogButton(dialog, '+ 添加模型'));
    expect(await screen.findByText('模型 m-a 已存在')).toBeTruthy();
  });

  it('editing a model pre-fills the dialog and saves meta without touching models', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getByRole('button', { name: '编辑模型 m-b' }));
    await screen.findByRole('dialog', { name: '编辑模型 m-b' });
    expect((screen.getByLabelText('模型 ID') as HTMLInputElement).value).toBe('m-b');
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() => expect(onPatch).toHaveBeenCalled());
    const patch = onPatch.mock.calls[0][0];
    expect(patch.models).toBeUndefined();
    expect(patch.models_meta['m-b'].image_input).toBe(true);
  });

  it('removing a model goes through confirmation and filters the list', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getByRole('button', { name: '移除 m-b' }));
    const dialog = await screen.findByRole('dialog', { name: '删除模型' });
    fireEvent.click(dialogButton(dialog, '移除 m-b'));
    await waitFor(() => expect(onPatch).toHaveBeenCalled());
    const patch = onPatch.mock.calls[0][0];
    expect(patch.models).toEqual(['m-a']);
    expect(patch.models_meta['m-b']).toBeUndefined();
  });

  it('per-model test writes the verdict into the row', async () => {
    const { onTestModel } = setup();
    fireEvent.click(screen.getByRole('button', { name: '测试 m-a 连接' }));
    await waitFor(() => expect(onTestModel).toHaveBeenCalledWith('m-a'));
    expect(await screen.findByText(/连通正常/)).toBeTruthy();
    expect(screen.getByText(/120 ms/)).toBeTruthy();
  });

  it('model dialog JSON editor applies hand edits back into the saved meta', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getByRole('button', { name: '编辑模型 m-b' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑模型 m-b' });
    // the config editor is collapsed by default; expand it first (scoped to
    // this dialog: the provider config section has its own 编辑配置 button)
    fireEvent.click(within(dialog).getByRole('button', { name: '编辑配置' }));
    const json = await screen.findByLabelText('模型配置文件');
    // Hand-edit the JSON in the ZCode shape: compat, thinking levels, limits
    const doc = JSON.parse((json as HTMLTextAreaElement).value);
    doc.compat = { maxTokensField: 'max_tokens' };
    doc.reasoning = { enabled: true, variants: ['low', 'high', 'max'], defaultVariant: 'max' };
    doc.limit = { context: 900000, output: 131072 };
    fireEvent.change(json, { target: { value: JSON.stringify(doc, null, 2) } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    await waitFor(() => expect(onPatch).toHaveBeenCalled());
    const patch = onPatch.mock.calls[0][0];
    expect(patch.models_meta['m-b'].compat).toEqual({ maxTokensField: 'max_tokens' });
    expect(patch.models_meta['m-b'].thinking_variants).toEqual(['low', 'high', 'max']);
    expect(patch.models_meta['m-b'].thinking_default).toBe('max');
    expect(patch.models_meta['m-b'].context_window).toBe(900000);
    expect(patch.models_meta['m-b'].max_output_tokens).toBe(131072);
  });

  it('malformed JSON blocks saving with an error instead of saving garbage', async () => {
    const { onPatch } = setup();
    fireEvent.click(screen.getByRole('button', { name: '编辑模型 m-b' }));
    const dialog = await screen.findByRole('dialog', { name: '编辑模型 m-b' });
    fireEvent.click(within(dialog).getByRole('button', { name: '编辑配置' }));
    const json = await screen.findByLabelText('模型配置文件');
    fireEvent.change(json, { target: { value: '{ not json' } });
    fireEvent.click(screen.getByRole('button', { name: '保存' }));
    expect(await screen.findByText(/JSON 无效/)).toBeTruthy();
    expect(onPatch).not.toHaveBeenCalled();
  });
});
