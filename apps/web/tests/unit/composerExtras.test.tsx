/**
 * @file composerExtras
 * @description Composer bottom-bar extras: the model picker writes
 * llm.default_provider + llm.default_model, the reasoning picker writes
 * llm.reasoning_effort and stays disabled unless the selected model declares
 * thinking support, and the context ring renders the usage popover (empty
 * state when no live context exists).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, setCalls } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  setCalls: [] as Array<{ key: string; value: unknown }>,
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ChatComposer } from '@/widgets/chat/ChatComposer';
import type { LlmProvider } from '@/api/types';
import { initI18n } from '@/i18n';

const composerStub = {
  draft: '',
  setDraft: vi.fn(),
  sending: false,
  llmMissing: false,
  send: vi.fn(),
};

const PROVIDERS = [
  {
    id: 'p1',
    display_name: '智谱',
    enabled: true,
    has_api_key: true,
    models: ['glm-think', 'glm-plain'],
    models_meta: { 'glm-think': { thinking: true, image_input: true } },
  },
] as unknown as LlmProvider[];

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  setCalls.length = 0;
  callCapabilityMock.mockReset().mockImplementation((_domain: string, name: string, payload?) => {
    if (name === 'get_setting') {
      return Promise.resolve({ key: payload?.key, value: '' });
    }
    if (name === 'set_setting') {
      setCalls.push({ key: payload?.key, value: payload?.value });
      return Promise.resolve({});
    }
    if (name === 'context_status') {
      return Promise.reject(new Error('no live context'));
    }
    return Promise.resolve({});
  });
});

function renderComposer() {
  return render(
    <ChatComposer
      composer={composerStub}
      placeholder=""
      className="chat-input"
      providers={PROVIDERS}
    />
  );
}

describe('ChatComposer extras', () => {
  it('renders ring, model picker, reasoning picker and send', () => {
    const { container } = renderComposer();
    expect(container.querySelector('.ctx-ring')).not.toBeNull();
    expect(screen.getByRole('button', { name: '选择模型' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '思考强度' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '发送' })).toBeTruthy();
  });

  it('picking a model writes the provider and model settings', async () => {
    renderComposer();
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
    fireEvent.click(screen.getByText('glm-plain'));
    await waitFor(() => {
      const keys = setCalls.map((c) => c.key);
      expect(keys).toContain('llm.default_model');
      expect(keys).toContain('llm.default_provider');
    });
    expect(setCalls.find((c) => c.key === 'llm.default_model')?.value).toBe('glm-plain');
    expect(setCalls.find((c) => c.key === 'llm.default_provider')?.value).toBe('p1');
  });

  it('reasoning picker is disabled for models without thinking and writes the level otherwise', async () => {
    renderComposer();
    // default model glm-plain has no thinking meta -> disabled
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
    fireEvent.click(screen.getByText('glm-plain'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '思考强度' })).toHaveProperty('disabled', true)
    );
    // switch back to the thinking-capable model and pick 高
    fireEvent.click(screen.getByRole('button', { name: '选择模型' }));
    fireEvent.click(screen.getByText('glm-think'));
    const trigger = screen.getByRole('button', { name: '思考强度' });
    await waitFor(() => expect(trigger).toHaveProperty('disabled', false));
    fireEvent.click(trigger);
    fireEvent.click(screen.getByText('高'));
    await waitFor(() => {
      const entry = setCalls.find((c) => c.key === 'llm.reasoning_effort');
      expect(entry?.value).toBe('medium');
    });
  });

  it('context ring popover degrades to the empty state without live context', async () => {
    renderComposer();
    fireEvent.click(screen.getByRole('button', { name: '上下文用量' }));
    expect(screen.getByText('上下文窗口')).toBeTruthy();
    await waitFor(() => expect(screen.getByText(/还没有上下文用量/)).toBeTruthy());
  });
});
