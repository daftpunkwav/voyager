/**
 * @file types/llm.ts
 * @description LLM domain types: API formats, providers (legacy and current shapes),
 * per-agent LLM overrides and speaking styles.
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

/** Authoritative API formats; the legacy openai/google/ollama enum is retired. */
export type LlmApiFormat = 'chat' | 'anthropic' | 'responses';

/** Per-model metadata (llm provider models_meta), mirroring the ZCode config
 *  shape: capability flags decide composer affordances (attachments / thinking
 *  picker), thinking_variants + thinking_default describe the supported
 *  thinking levels and their default, the token budgets feed the agent's
 *  context budget via agent.context.model_profiles, enabled=false hides the
 *  model from default resolution, and compat carries free-form
 *  provider-specific wire tweaks editable only through the JSON config file. */
export interface LlmModelMeta {
  name?: string;
  image_input?: boolean;
  audio_input?: boolean;
  video_input?: boolean;
  thinking?: boolean;
  thinking_variants?: string[];
  thinking_default?: string;
  context_window?: number;
  max_output_tokens?: number;
  output_modalities?: string[];
  enabled?: boolean;
  compat?: Record<string, string | number | boolean | null>;
}

/** Provider shape returned by the llm service list_providers capability.
 *  Keys are never returned (pages read has_api_key); writing a key goes only
 *  through llm.set_api_key. There is no provider-level default model: an
 *  untagged call resolves to the first enabled model of `models`. */
export interface LlmProvider {
  id: string;
  preset_id: string;
  display_name: string;
  base_url: string;
  api_format: LlmApiFormat;
  models: string[];
  models_meta: Record<string, LlmModelMeta>;
  enabled: boolean;
  custom: boolean;
  has_api_key: boolean;
}

/** Shape returned by llm.test_connection (ok/error/latency_ms/model; no reply/success).
 *  Lives in the domain type layer instead of LlmSettingsSection to avoid a
 *  child-to-parent type import cycle. */
export interface LlmTestOutcome {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  error?: string;
}
