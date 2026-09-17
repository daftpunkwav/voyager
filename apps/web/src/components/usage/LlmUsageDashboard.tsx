/**
 * @file LlmUsageDashboard
 * @description Single-screen LLM usage dashboard: KPI cards, heatmap, donut, stacked bars, and recent calls, with a day-range switch.
 *
 * Responsibilities:
 * - Query the LLM usage summary for a selectable day range
 * - Compose KPI cards, heatmap, donut, stacked bars and the recent-calls table
 * - Render loading, backend-unreachable and empty states
 */

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getLlmUsage } from '@/api/usage';
import type { LlmUsageSummary } from '@/api/types';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { backendUnreachable } from '@/utils/errors';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { GLASS_CHIP, GLASS_OUTER } from '@/constants/glassTokens';
import { formatTokenCount } from '@/utils/formatTokens';
import { formatDateTime } from '@/i18n';
import { DailyTokenQuotaCard } from './DailyTokenQuotaCard';
import { UsageDonut } from './UsageDonut';
import { UsageHeatmap } from './UsageHeatmap';
import { UsageKpiCards } from './UsageKpiCards';
import { UsageStackedBars } from './UsageStackedBars';

const DAYS_OPTIONS = [7, 30] as const;

/** Recent calls rendered before the list scrolls (backend default caps at 20). */
const RECENT_VISIBLE = 10;

function fmtTs(ts: string | null): string {
  if (!ts) return '—';
  // Locale follows i18n; unparseable input passes through (formatDateTime contract)
  return formatDateTime(ts, {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizeUsage(raw: unknown): LlmUsageSummary {
  const u = raw as Partial<LlmUsageSummary>;
  const byModel = Array.isArray(u.by_model)
    ? u.by_model.map((m) => ({
        model: m.model ?? 'unknown',
        label: m.label,
        provider: m.provider,
        input: m.input ?? 0,
        output: m.output ?? 0,
        total_tokens: m.total_tokens ?? m.input + m.output,
        calls: m.calls ?? 0,
        cost: m.cost,
      }))
    : [];
  const byDay = Array.isArray(u.by_day)
    ? u.by_day.map((d) => ({
        date: d.date ?? '',
        input: d.input ?? 0,
        output: d.output ?? 0,
        total_tokens: d.total_tokens ?? d.input + d.output,
        prompt_cached_tokens: d.prompt_cached_tokens,
        prompt_uncached_tokens: d.prompt_uncached_tokens,
        completion_tokens: d.completion_tokens,
        calls: d.calls ?? 0,
        cost: d.cost,
        by_model: d.by_model,
      }))
    : [];
  const totalInput = u.total_input_tokens ?? byDay.reduce((s, d) => s + d.input, 0);
  const totalOutput = u.total_output_tokens ?? byDay.reduce((s, d) => s + d.output, 0);
  return {
    total_input_tokens: totalInput,
    total_output_tokens: totalOutput,
    total_cost: u.total_cost,
    by_model: byModel,
    by_day: byDay,
    totals: u.totals,
    top: u.top,
    by_provider: u.by_provider,
    heatmap: u.heatmap,
    recent: u.recent,
  };
}

/** One-screen usage dashboard */
export function LlmUsageDashboard() {
  const { t } = useTranslation('usage');
  const [days, setDays] = useState<(typeof DAYS_OPTIONS)[number]>(30);
  const queryClient = useQueryClient();

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ['llm-usage', days],
    queryFn: async () => {
      // api/usage.getLlmUsage returns LlmUsageSummary directly (the envelope is already unwrapped in the api layer)
      return normalizeUsage(await getLlmUsage(days));
    },
  });

  const usage = data;

  return (
    <section className={`usage-dashboard ${GLASS_OUTER}`}>
      {/* The daily quota card reads the agent Meter and is a separate query from the llm history stats:
          it always renders so loading/failure of the stats does not take it down too. */}
      <DailyTokenQuotaCard />

      {isLoading && (
        <div className="page-scaffold__state">
          <LoadingSpinner label={t('usage:dashboard.loading')} />
        </div>
      )}
      {isError && (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('usage:dashboard.unavailable')}
            description={(error as Error | null)?.message || backendUnreachable()}
            icon={EmptyStateIcons.usage}
            onRetry={() => void refetch()}
          />
        </div>
      )}

      {usage && (
        <>
          <div className="usage-toolbar">
            <div className="usage-toolbar-left">
              <span className="usage-toolbar-label">{t('usage:dashboard.range')}</span>
              <div className="layout-switch">
                {DAYS_OPTIONS.map((d) => (
                  <button
                    key={d}
                    type="button"
                    className={days === d ? 'active' : ''}
                    onClick={() => setDays(d)}
                  >
                    {t('usage:dashboard.lastDays', { days: d })}
                  </button>
                ))}
              </div>
            </div>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              disabled={isFetching}
              onClick={() => {
                // The daily quota is a separate query (agent Meter); invalidate and refetch it together on refresh
                void queryClient.invalidateQueries({ queryKey: ['agent-daily-quota'] });
                void refetch();
              }}
            >
              {t('usage:dashboard.refresh')}
            </button>
          </div>

          <div className="usage-dashboard-body">
            <UsageKpiCards usage={usage} />
            <div className="usage-mid-row">
              <UsageHeatmap heatmap={usage.heatmap} days={days} />
              <UsageDonut usage={usage} />
            </div>
            <UsageStackedBars usage={usage} />
            {usage.recent && usage.recent.length > 0 ? (
              <div className={`${GLASS_CHIP} usage-recent`}>
                <h3 className="usage-panel-title">{t('usage:recent.title')}</h3>
                <ul className="usage-recent-list">
                  {usage.recent.slice(0, RECENT_VISIBLE).map((call) => (
                    <li key={call.id}>
                      <span className="usage-recent-ts">{fmtTs(call.created_at)}</span>
                      <span className="usage-recent-model">
                        {call.label ||
                          (call.provider && call.provider !== 'unknown'
                            ? `${call.provider}/${call.model}`
                            : call.model)}
                      </span>
                      {call.agent_id ? <span className="badge">{call.agent_id}</span> : null}
                      <span className="usage-recent-tokens">
                        {t('usage:recent.tokens', {
                          cached: formatTokenCount(call.prompt_cached_tokens),
                          uncached: formatTokenCount(call.prompt_uncached_tokens),
                          completion: formatTokenCount(call.completion_tokens),
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </>
      )}
    </section>
  );
}
