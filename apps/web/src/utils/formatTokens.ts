/**
 * @file formatTokens
 * @description Token-count formatting with Chinese magnitude units.
 *
 * The magnitude suffixes are display copy and resolve through the chat ns at
 * call time. The divisors stay locale-independent, so the English suffixes use
 * multiplier notation ("×100M") to keep the rendered value unambiguous.
 */

import { i18n } from '@/i18n';

/** Display formatting for token counts (Chinese magnitude units). */
export function formatTokenCount(n: number | undefined | null): string {
  const v = Number(n) || 0;
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}${i18n.t('chat:tokens.unitYi')}`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(1)}${i18n.t('chat:tokens.unitWan')}`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(Math.round(v));
}

export function formatTokenPercent(part: number, total: number): string {
  if (!total) return '0%';
  const pct = (part / total) * 100;
  if (pct >= 10) return `${pct.toFixed(0)}%`;
  return `${pct.toFixed(1)}%`;
}
