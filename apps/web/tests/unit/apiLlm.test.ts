/**
 * @file apiLlm
 * @description Pins the llm domain contract (api/llm.ts): capability names
 * and argument shapes, the write-only key storage, and the
 * firstEnabledModel read-side resolution.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({
  callCapability: callCapabilityMock,
  unwrapDataField: (r: unknown) =>
    r && typeof r === 'object' && 'data' in (r as object) ? (r as { data: unknown }).data : r,
}));

import {
  listProviders,
  addProvider,
  updateProvider,
  firstEnabledModel,
  setApiKey,
  testConnection,
  listRemoteModels,
  removeProvider,
} from '@/api/llm';
import type { LlmProvider } from '@/api/types';

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('api/llm bridge wrappers', () => {
  it('listProviders unwraps the payload', async () => {
    callCapabilityMock.mockResolvedValue({ data: [{ id: 'p1' }] });
    await expect(listProviders()).resolves.toEqual([{ id: 'p1' }]);
    // callCapability's default arg applies at its own definition site:
    // the mock observes the two explicit arguments only.
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_providers');
  });

  it('addProvider forwards the descriptor', async () => {
    callCapabilityMock.mockResolvedValue({ data: { id: 'new' } });
    await expect(addProvider({ display_name: 'X' })).resolves.toEqual({ id: 'new' });
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'add_provider', {
      display_name: 'X',
    });
  });

  it('updateProvider prefixes provider_id and never carries a key', async () => {
    callCapabilityMock.mockResolvedValue({});
    await updateProvider('p1', { display_name: 'Y', enabled: false });
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'update_provider', {
      provider_id: 'p1',
      display_name: 'Y',
      enabled: false,
    });
  });

  it('setApiKey is write-only (key goes to set_api_key)', async () => {
    callCapabilityMock.mockResolvedValue({});
    await setApiKey('p1', 'sk-secret');
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'set_api_key', {
      provider_id: 'p1',
      api_key: 'sk-secret',
    });
  });

  it('testConnection and listRemoteModels pass provider/model through', async () => {
    callCapabilityMock.mockResolvedValue({ data: { ok: true } });
    await testConnection('p1', 'm1');
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'test_connection', {
      provider_id: 'p1',
      model: 'm1',
    });

    callCapabilityMock.mockResolvedValue({ data: { models: ['a', 'b'] } });
    await expect(listRemoteModels('p1')).resolves.toEqual(['a', 'b']);
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'list_remote_models', {
      provider_id: 'p1',
    });
  });

  it('removeProvider routes by provider_id', async () => {
    callCapabilityMock.mockResolvedValue({});
    await removeProvider('p1');
    expect(callCapabilityMock).toHaveBeenCalledWith('llm', 'remove_provider', {
      provider_id: 'p1',
    });
  });
});

describe('api/llm firstEnabledModel', () => {
  const provider = (models: string[], meta?: LlmProvider['models_meta']): LlmProvider =>
    ({ id: 'p', models, models_meta: meta }) as LlmProvider;

  it('returns empty for a missing provider', () => {
    expect(firstEnabledModel(null)).toBe('');
    expect(firstEnabledModel(undefined)).toBe('');
  });

  it('skips models explicitly disabled in models_meta', () => {
    const p = provider(['a', 'b', 'c'], { a: { enabled: false }, b: { enabled: true } });
    expect(firstEnabledModel(p)).toBe('b');
  });

  it('treats models without meta as enabled', () => {
    expect(firstEnabledModel(provider(['a', 'b']))).toBe('a');
  });

  it('falls back to the first model when every model is disabled', () => {
    const p = provider(['a', 'b'], { a: { enabled: false }, b: { enabled: false } });
    expect(firstEnabledModel(p)).toBe('a');
  });

  it('returns empty when the provider has no models', () => {
    expect(firstEnabledModel(provider([]))).toBe('');
  });
});
