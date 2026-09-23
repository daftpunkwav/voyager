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
  total_cost?: number;
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
    cost?: number;
  };
  top?: {
    model: string;
    provider?: string;
    label?: string;
    total_tokens: number;
  };
  by_model: Array<{
    model: string;
    label?: string;
    provider?: string;
    input: number;
    output: number;
    total_tokens: number;
    /** Output tokens spent on reasoning (thinking models only). */
    reasoning_tokens?: number;
    calls: number;
    cost?: number;
  }>;
  by_provider?: Array<{
    provider: string;
    input: number;
    output: number;
    total_tokens: number;
    calls: number;
    cost?: number;
  }>;
  by_day: Array<{
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
    cost?: number;
    by_model?: Array<{
      model: string;
      input: number;
      output: number;
      total_tokens: number;
      calls: number;
    }>;
  }>;
  heatmap?: Array<{ date: string; calls: number; intensity: number }>;
  recent?: Array<{
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
  }>;
}
