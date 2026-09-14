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
import type { LlmBuiltinPreset, LlmProvider, LlmTestOutcome } from '@/api/types';

export function listProviders(): Promise<LlmProvider[]> {
  return callCapability<LlmProvider[]>('llm', 'list_providers').then(
    unwrapDataField<LlmProvider[]>
  );
}

/** Built-in catalog presets; the backend catalog is the source of truth. */
export function listBuiltinProviders(): Promise<LlmBuiltinPreset[]> {
  return callCapability<LlmBuiltinPreset[]>('llm', 'list_builtin_providers').then(
    unwrapDataField<LlmBuiltinPreset[]>
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
      | 'display_name'
      | 'base_url'
      | 'api_format'
      | 'models'
      | 'models_meta'
      | 'default_model'
      | 'enabled'
    >
  >
): Promise<unknown> {
  return callCapability('llm', 'update_provider', { provider_id: providerId, ...patch }).then(
    unwrapDataField
  );
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

export function removeProvider(providerId: string): Promise<unknown> {
  return callCapability('llm', 'remove_provider', { provider_id: providerId }).then(
    unwrapDataField
  );
}
