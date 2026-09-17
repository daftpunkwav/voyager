/**
 * @file llm.ts
 * @description LLM domain (llm service): provider CRUD, API keys, connectivity tests.
 *
 * All functions return payloads directly, without a {data} envelope. The
 * settings-side llm.default_provider key is intentionally not read/written
 * here: the settings form domain calls callCapability directly (a sanctioned
 * exception).
 *
 * Responsibilities:
 * - Provider CRUD against the llm service (add / metadata patch / remove)
 * - Write-only API key storage; callers read back has_api_key, never the key
 * - Serve builtin provider presets and run connectivity tests
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';
import type { LlmProvider, LlmTestOutcome } from '@/api/types';

export function listProviders(): Promise<LlmProvider[]> {
  return callCapability<LlmProvider[]>('llm', 'list_providers').then(
    unwrapDataField<LlmProvider[]>
  );
}

export function addProvider(d: Record<string, unknown>): Promise<{ id: string }> {
  return callCapability<{ id: string }>('llm', 'add_provider', d).then(
    unwrapDataField<{ id: string }>
  );
}

/** Metadata patch (never the key; api_format is limited to chat/anthropic). */
export function updateProvider(
  providerId: string,
  patch: Partial<
    Pick<
      LlmProvider,
      'display_name' | 'base_url' | 'api_format' | 'models' | 'models_meta' | 'enabled'
    >
  >
): Promise<unknown> {
  return callCapability('llm', 'update_provider', { provider_id: providerId, ...patch }).then(
    unwrapDataField
  );
}

/** First enabled model of a provider (models_meta enabled=False entries are
 *  skipped); falls back to the first model, else empty. The read-side twin of
 *  the backend's effective_model resolution. */
export function firstEnabledModel(p: LlmProvider | null | undefined): string {
  if (!p) return '';
  const meta = p.models_meta ?? {};
  for (const m of p.models) {
    const fields = meta[m];
    if (!fields || fields.enabled !== false) return m;
  }
  return p.models[0] ?? '';
}

/** Write-only key storage: keys persist via secrets and are never returned; pages read has_api_key instead. */
export function setApiKey(providerId: string, apiKey: string): Promise<unknown> {
  return callCapability('llm', 'set_api_key', { provider_id: providerId, api_key: apiKey }).then(
    unwrapDataField
  );
}

export function testConnection(providerId: string, model: string): Promise<LlmTestOutcome> {
  return callCapability<LlmTestOutcome>('llm', 'test_connection', {
    provider_id: providerId,
    model,
  }).then(unwrapDataField<LlmTestOutcome>);
}

/** Live model catalog from the provider's GET /models endpoint. */
export function listRemoteModels(providerId: string): Promise<string[]> {
  return callCapability<{ models: string[] }>('llm', 'list_remote_models', {
    provider_id: providerId,
  }).then((r) => unwrapDataField<{ models: string[] }>(r).models);
}

export function removeProvider(providerId: string): Promise<unknown> {
  return callCapability('llm', 'remove_provider', { provider_id: providerId }).then(
    unwrapDataField
  );
}
