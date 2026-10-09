/**
 * @file types/usage.ts
 * @description Usage domain types (LLM token statistics; cost fields are optional because
 * the backend does not persist prices and never invents them).
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

export interface LlmUsageSummary {
  total_input_tokens: number;
  total_output_tokens: number;
  totals?: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    prompt_cached_tokens: number;
    prompt_uncached_tokens: number;
    completion_tokens: number;
    /** Output tokens the model spent on reasoning (thinking models only;
     *  absent when the provider does not report the split). */
    reasoning_tokens?: number;
    calls: number;
    /** Read-side converted cost (get_usage_stats attaches cost_usd only for priced models). */
    cost_usd?: number;
  };
  top?: {
    model: string;
    provider?: string;
    label?: string;
    total_tokens: number;
  };
  by_model: {
    model: string;
    label?: string;
    provider?: string;
    input: number;
    output: number;
    total_tokens: number;
    /** Output tokens spent on reasoning (thinking models only). */
    reasoning_tokens?: number;
    calls: number;
    /** Read-side converted cost (get_usage_stats attaches cost_usd only for priced models). */
    cost_usd?: number;
  }[];
  by_provider?: {
    provider: string;
    input: number;
    output: number;
    total_tokens: number;
    calls: number;
    /** Read-side converted cost (get_usage_stats attaches cost_usd only for priced models). */
    cost_usd?: number;
  }[];
  by_day: {
    date: string;
    input: number;
    output: number;
    total_tokens: number;
    prompt_cached_tokens: number;
    prompt_uncached_tokens: number;
    completion_tokens: number;
    /** Output tokens spent on reasoning (thinking models only). */
    reasoning_tokens?: number;
    calls: number;
    /** Read-side converted cost (get_usage_stats attaches cost_usd only for priced models). */
    cost_usd?: number;
    by_model?: {
      model: string;
      input: number;
      output: number;
      total_tokens: number;
      calls: number;
    }[];
  }[];
  heatmap?: { date: string; calls: number; intensity: number }[];
  recent?: {
    id: string;
    created_at: string;
    label?: string;
    provider?: string;
    model: string;
    agent_id?: string;
    prompt_cached_tokens: number;
    prompt_uncached_tokens: number;
    completion_tokens: number;
    /** Output tokens spent on reasoning (thinking models only). */
    reasoning_tokens?: number;
    ok: boolean;
  }[];
}
