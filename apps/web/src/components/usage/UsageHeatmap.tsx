/**
 * @file UsageHeatmap
 * @description GitHub-style activity heatmap of daily LLM calls laid out in
 * week columns. The grid always spans the selected day window (from
 * today-(days-1) to today), so quiet stretches render as empty cells instead
 * of collapsing the chart to only the days that had traffic.
 *
 * Responsibilities:
 * - Lay per-day call counts out into GitHub-style week columns
 * - Color cells by intensity using local-calendar day keys
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';

interface UsageHeatmapProps {
  heatmap: LlmUsageSummary['heatmap'];
  /** Selected window length in days; the grid covers exactly this range. */
  days: number;
}

interface HeatCell {
  date: string;
  calls: number;
  intensity: number;
}

/** Local calendar day as YYYY-MM-DD (do not use toISOString — it shifts the day via UTC) */
function ymdLocal(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function normalizeHeatmap(raw: LlmUsageSummary['heatmap']): Map<string, number> {
  const calls = new Map<string, number>();
  if (!raw) return calls;
  for (const c of raw) calls.set(c.date, c.calls);
  return calls;
}

/** Lays the selected window out into GitHub-style week columns (7 rows x N
 *  weeks, Sunday-aligned). Days outside the window become null pads. */
function buildWeekColumns(calls: Map<string, number>, days: number) {
  if (days <= 0) return [] as Array<Array<HeatCell | null>>;

  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const first = new Date(today);
  first.setDate(first.getDate() - (days - 1));

  // Align the start to Sunday
  const start = new Date(first);
  start.setDate(start.getDate() - start.getDay());

  const columns: Array<Array<HeatCell | null>> = [];
  const cursor = new Date(start);
  let col: Array<HeatCell | null> = [];

  while (cursor <= today) {
    const key = ymdLocal(cursor);
    const inWindow = cursor >= first;
    const dayCalls = calls.get(key) ?? 0;
    col.push(inWindow ? { date: key, calls: dayCalls, intensity: dayCalls } : null);
    if (col.length === 7) {
      columns.push(col);
      col = [];
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  if (col.length) columns.push(col);
  return columns;
}

/** Intensity by rank within the window: quartile tiers stay readable when a
 *  single busy day would otherwise flatten every other cell to level 1. */
function levelOf(calls: number, maxCalls: number): 0 | 1 | 2 | 3 {
  if (calls <= 0 || maxCalls <= 0) return 0;
  const ratio = calls / maxCalls;
  if (ratio < 0.25) return 1;
  if (ratio < 0.6) return 2;
  return 3;
}

/** GitHub-style activity heatmap (week-column layout) */
export function UsageHeatmap({ heatmap, days }: UsageHeatmapProps) {
  const { t } = useTranslation('usage');
  const { weeks, maxCalls } = useMemo(() => {
    const calls = normalizeHeatmap(heatmap);
    return {
      weeks: buildWeekColumns(calls, days),
      maxCalls: Math.max(1, ...[...calls.values()]),
    };
  }, [heatmap, days]);

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-heat-panel`}>
      <div className="usage-panel-head">
        <h3 className="usage-panel-title">{t('usage:heat.title')}</h3>
        <div className="usage-heat-legend" aria-hidden>
          <span>{t('usage:heat.less')}</span>
          <span className="usage-heat-swatch" data-level="0" />
          <span className="usage-heat-swatch" data-level="1" />
          <span className="usage-heat-swatch" data-level="2" />
          <span className="usage-heat-swatch" data-level="3" />
          <span>{t('usage:heat.more')}</span>
        </div>
      </div>
      <div className="usage-heat-wrap">
        <div className="usage-heat-grid" role="img" aria-label={t('usage:heat.aria')}>
          {weeks.map((week, wi) => (
            <div key={wi} className="usage-heat-week">
              {week.map((cell, di) =>
                cell ? (
                  <div
                    key={cell.date}
                    className="usage-heat-cell"
                    data-level={levelOf(cell.calls, maxCalls)}
                    title={t('usage:heat.cellTitle', { date: cell.date, calls: cell.calls })}
                  />
                ) : (
                  <div key={`pad-${wi}-${di}`} className="usage-heat-cell is-pad" />
                )
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
