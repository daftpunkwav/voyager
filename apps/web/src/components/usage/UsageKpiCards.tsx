/**
 * @file UsageKpiCards
 * @description KPI summary cards for LLM usage: token totals, cache hit/miss split, call count, and top model.
 *
 * Responsibilities:
 * - Summarize token totals, cache hit/miss split, call count and top model
 * - Render purely from the usage prop with no fetching of its own
 */

import type { LlmUsageSummary } from '@/api/types';
import { useTranslation } from 'react-i18next';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

interface UsageKpiCardsProps {
  usage: LlmUsageSummary;
}

/** Values the backend did not report stay null and render as a dash — never estimated. */
function normalizeTotals(usage: LlmUsageSummary) {
  const t = usage.totals;
  return {
    total_tokens: t?.total_tokens ?? usage.total_input_tokens + usage.total_output_tokens,
    prompt_cached_tokens: t?.prompt_cached_tokens ?? null,
    prompt_uncached_tokens: t?.prompt_uncached_tokens ?? null,
    completion_tokens: t?.completion_tokens ?? usage.total_output_tokens,
    calls: t?.calls ?? null,
  };
}

function tokensOrDash(value: number | null): string {
  return value == null ? '—' : formatTokenCount(value);
}

export function UsageKpiCards({ usage }: UsageKpiCardsProps) {
  const { t } = useTranslation('usage');
  const totals = normalizeTotals(usage);
  const top = usage.top;
  const topLabel =
    top?.label ||
    (top ? `${top.provider ?? 'unknown'}/${top.model}` : null) ||
    usage.by_model[0]?.label ||
    usage.by_model[0]?.model ||
    '—';
  const topTokens = top?.total_tokens ?? usage.by_model[0]?.total_tokens;
  const topShare =
    topTokens != null && totals.total_tokens > 0
      ? t('usage:kpi.share', { value: formatTokenPercent(topTokens, totals.total_tokens) })
      : undefined;

  const items = [
    { label: t('usage:kpi.totalTokens'), value: formatTokenCount(totals.total_tokens) },
    { label: t('usage:kpi.cached'), value: tokensOrDash(totals.prompt_cached_tokens) },
    { label: t('usage:kpi.uncached'), value: tokensOrDash(totals.prompt_uncached_tokens) },
    { label: t('usage:kpi.output'), value: formatTokenCount(totals.completion_tokens) },
    { label: t('usage:kpi.calls'), value: totals.calls == null ? '—' : String(totals.calls) },
    {
      label: t('usage:kpi.topModel'),
      value: topLabel,
      sub: topShare,
    },
  ];

  return (
    <div className="usage-kpi-grid">
      {items.map((item) => (
        <div key={item.label} className={`${GLASS_CHIP} usage-kpi-card`}>
          <div className="usage-kpi-label">{item.label}</div>
          <div className="usage-kpi-value" title={item.value}>
            {item.value}
          </div>
          {item.sub ? <div className="usage-kpi-sub">{item.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}
