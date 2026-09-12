/**
 * @file quotaGuard.ts
 * @description Client-side daily token quota guard checked before chat sends.
 *
 * The backend metered_llm remains the authoritative enforcement; this guard
 * only gives earlier feedback and saves one wasted request. Query failures
 * soft-fail open (no prompt) — the backend's quota-degradation reply is the
 * backstop.
 *
 * Responsibilities:
 * - Evaluate the get_resource_quota snapshot into allow / warn / block
 *   decisions (pure evaluateQuota, no React dependency)
 * - Soft-fail open when the quota query fails
 * - Resolve block/warn copy through the chat namespace at call time
 *
 * This module must not depend on UI-layer components.
 */

import { getResourceQuota } from '@/api/agent';
import { i18n } from '@/i18n';

/** get_resource_quota snapshot: today's usage and limit (0 = unlimited). */
export interface QuotaSnapshot {
  tokens_used_today: number;
  daily_tokens: number;
}

export type QuotaGuardResult =
  { action: 'allow' } | { action: 'warn'; ratio: number } | { action: 'block'; reason: string };

/** Pre-send warn threshold: warn at >= 80%; the usage page's progress bar uses 0.9 — the two are intentionally different. */
export const QUOTA_WARN_RATIO = 0.8;

/** Block reason copy; resolves through the chat ns at call time (replaces the
 *  former hard-coded QUOTA_BLOCK_MESSAGE constant so it follows the UI language). */
export function quotaBlockMessage(): string {
  return i18n.t('chat:quota.block');
}

/** Warn toast text (ratio 0-1). */
export function quotaWarnMessage(ratio: number): string {
  return i18n.t('chat:quota.warn', { pct: Math.round(ratio * 100) });
}

/** Pure decision: limit<=0 (unlimited) → allow; exhausted → block; >= 80% → warn. No React dependency. */
export function evaluateQuota(snapshot: QuotaSnapshot): QuotaGuardResult {
  const { tokens_used_today: used, daily_tokens: limit } = snapshot;
  if (!Number.isFinite(limit) || limit <= 0) return { action: 'allow' };
  if (used >= limit) return { action: 'block', reason: quotaBlockMessage() };
  const ratio = used / limit;
  if (ratio >= QUOTA_WARN_RATIO) return { action: 'warn', ratio };
  return { action: 'allow' };
}

/** Fetch the quota and evaluate; query failures soft-fail open (the backend metered_llm is the backstop). */
export async function fetchQuotaGuard(): Promise<QuotaGuardResult> {
  try {
    const snapshot = await getResourceQuota();
    return evaluateQuota(snapshot);
  } catch {
    return { action: 'allow' };
  }
}
