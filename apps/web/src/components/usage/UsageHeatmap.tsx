/**
 * @file UsageHeatmap
 * @description GitHub-style activity heatmap of daily LLM calls laid out in week columns.
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

function normalizeHeatmap(raw: LlmUsageSummary['heatmap']): HeatCell[] {
  if (!raw || raw.length === 0) return [];
  const maxCalls = Math.max(...raw.map((c) => c.calls), 1);
  return raw.map((c) => ({
    date: c.date,
    calls: c.calls,
    intensity: c.intensity ?? c.calls / maxCalls,
  }));
}

/** Lays the per-day data out into GitHub-style week columns (7 rows x N weeks) */
function buildWeekColumns(heatmap: HeatCell[]) {
  if (!heatmap.length) return [] as Array<Array<HeatCell | null>>;

  const byDate = new Map(heatmap.map((c) => [c.date, c]));
  const first = new Date(`${heatmap[0]?.date ?? ''}T12:00:00`);
  const last = new Date(`${heatmap[heatmap.length - 1]?.date ?? ''}T12:00:00`);

  // Align the start to Sunday
  const start = new Date(first);
  start.setDate(start.getDate() - start.getDay());

  const end = new Date(last);
  end.setDate(end.getDate() + (6 - end.getDay()));

  const columns: Array<Array<HeatCell | null>> = [];
  const cursor = new Date(start);
  let col: Array<HeatCell | null> = [];

  while (cursor <= end) {
    const key = ymdLocal(cursor);
    const inRange =
      key >= (heatmap[0]?.date ?? '') && key <= (heatmap[heatmap.length - 1]?.date ?? '');
    col.push(inRange ? (byDate.get(key) ?? { date: key, calls: 0, intensity: 0 }) : null);
    if (col.length === 7) {
      columns.push(col);
      col = [];
    }
    cursor.setDate(cursor.getDate() + 1);
  }
  if (col.length) columns.push(col);
  return columns;
}

function levelOf(intensity: number): 0 | 1 | 2 | 3 {
  if (intensity <= 0) return 0;
  if (intensity < 0.34) return 1;
  if (intensity < 0.67) return 2;
  return 3;
}

/** GitHub-style activity heatmap (week-column layout) */
export function UsageHeatmap({ heatmap }: UsageHeatmapProps) {
  const { t } = useTranslation('usage');
  const weeks = useMemo(() => buildWeekColumns(normalizeHeatmap(heatmap)), [heatmap]);

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
                    data-level={levelOf(cell.intensity)}
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
