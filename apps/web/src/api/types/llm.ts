/**
 * @file types/llm.ts
 * @description LLM domain types: API formats, providers (legacy and current shapes),
 * per-agent LLM overrides and speaking styles.
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

/** Authoritative API formats: only these two remain; the legacy openai/google/ollama enum is retired. */
export type LlmApiFormat = 'chat' | 'anthropic';

/** Per-model metadata (llm provider models_meta): capability flags decide
 *  composer affordances (attachments / thinking picker), the token budgets
 *  feed the agent's context budget via agent.context.model_profiles. */
export interface LlmModelMeta {
  image_input?: boolean;
  audio_input?: boolean;
  video_input?: boolean;
  thinking?: boolean;
  context_window?: number;
  max_output_tokens?: number;
}

/** Provider shape returned by the llm service list_providers capability.
 *  Keys are never returned (pages read has_api_key); writing a key goes only
 *  through llm.set_api_key. */
export interface LlmProvider {
  id: string;
  preset_id: string;
  display_name: string;
  base_url: string;
  api_format: LlmApiFormat;
  models: string[];
  models_meta: Record<string, LlmModelMeta>;
  default_model: string;
  enabled: boolean;
  custom: boolean;
  has_api_key: boolean;
}

/** Per-agent LLM override config (runtime shape, as constructed and patched by
 *  LlmAgentOverrides defaults and llmConfig.createDefaultAgentLlmConfigs). */
export interface AgentLlmConfig {
  agent_id: string;
  provider_id: string | null;
  model_override: string | null;
  speaking_style: AgentSpeakingStyle;
}

/** Agent speaking style: a runtime string enum (the 8 values of
 *  llmConfig.SPEAKING_STYLE_OPTIONS); the legacy object shape has no remaining usage. */
export type AgentSpeakingStyle =
  'default' | 'warm' | 'sharp' | 'professional' | 'humorous' | 'concise' | 'mentor' | 'socratic';

/** Shape returned by llm.test_connection (ok/error/latency_ms/model; no reply/success).
 *  Lives in the domain type layer instead of LlmSettingsSection to avoid a
 *  child-to-parent type import cycle. */
export interface LlmTestOutcome {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  error?: string;
}

/** Shape returned by llm.list_builtin_providers (built-in catalog presets; the backend
 *  catalog is the source of truth). Previously defined inside LlmProviderAdd and
 *  moved here once api/llm.ts became the single access point. */
export interface LlmBuiltinPreset {
  preset_id: string;
  display_name: string;
  base_url: string;
  api_format: LlmApiFormat;
  models: string[];
}
