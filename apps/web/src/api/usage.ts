/**
 * @file usage.ts
 * @description LLM usage domain (llm service): thin layer for the usage dashboard.
 *
 * All functions return payloads directly, without a {data} envelope.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';
import type { LlmUsageSummary } from '@/api/types';

export function getLlmUsage(days = 30): Promise<LlmUsageSummary> {
  return callCapability('llm', 'get_usage_stats', { days }).then(unwrapDataField<LlmUsageSummary>);
}
