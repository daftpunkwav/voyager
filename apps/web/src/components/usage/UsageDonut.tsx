/**
 * @file UsageDonut
 * @description SVG donut chart of token usage by model or provider, with a legend and a model/provider mode switch.
 *
 * Responsibilities:
 * - Aggregate token usage by model or provider and draw the SVG donut
 * - Switch aggregation mode and render a color-keyed legend
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LlmUsageSummary } from '@/api/types';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { USAGE_CHART_COLORS } from '@/constants/usageChartColors';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

type DonutMode = 'model' | 'provider';

interface UsageDonutProps {
  usage: LlmUsageSummary;
}

interface Slice {
  key: string;
  tokens: number;
  color: string;
}

function polar(cx: number, cy: number, r: number, angle: number) {
  const rad = ((angle - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end);
  const e = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y}`;
}

function totalTokens(usage: LlmUsageSummary): number {
  return usage.totals?.total_tokens ?? usage.total_input_tokens + usage.total_output_tokens;
}

export function UsageDonut({ usage }: UsageDonutProps) {
  const { t } = useTranslation('usage');
  const [mode, setMode] = useState<DonutMode>('model');

  const slices: Slice[] = useMemo(() => {
    const rows =
      mode === 'model'
        ? usage.by_model.map((r) => ({
            key: r.label || r.model,
            tokens: r.total_tokens,
          }))
        : (usage.by_provider ?? []).map((r) => ({
            key: r.provider || '(unknown)',
            tokens: r.total_tokens,
          }));
    const sorted = [...rows].sort((a, b) => b.tokens - a.tokens);
    const top = sorted.slice(0, 5);
    const rest = sorted.slice(5).reduce((s, r) => s + r.tokens, 0);
    const list = [...top];
    if (rest > 0) list.push({ key: t('usage:donut.other'), tokens: rest });
    return list.map((r, i) => ({
      ...r,
      color: USAGE_CHART_COLORS[i % USAGE_CHART_COLORS.length] ?? '#8e8e93',
    }));
  }, [usage, mode, t]);

  const total = slices.reduce((s, x) => s + x.tokens, 0) || totalTokens(usage);
  const cx = 70;
  const cy = 70;
  const r = 52;
  const stroke = 16;

  let angle = 0;
  const arcs =
    total <= 0
      ? []
      : slices.map((slice) => {
          const sweep = (slice.tokens / total) * 360;
          const start = angle;
          const end = angle + Math.max(sweep, slice.tokens > 0 ? 0.5 : 0);
          angle = end;
          return { ...slice, start, end };
        });

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-donut-panel`}>
      <div className="usage-panel-head">
        <h3 className="usage-panel-title">{t('usage:donut.title')}</h3>
        <div className="layout-switch usage-mode-switch">
          <button
            type="button"
            className={mode === 'model' ? 'active' : ''}
            onClick={() => setMode('model')}
          >
            {t('usage:donut.modeModel')}
          </button>
          <button
            type="button"
            className={mode === 'provider' ? 'active' : ''}
            onClick={() => setMode('provider')}
          >
            {t('usage:donut.modeProvider')}
          </button>
        </div>
      </div>
      <div className="usage-donut-body">
        <svg viewBox="0 0 140 140" className="usage-donut-svg" aria-hidden>
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={stroke}
          />
          {arcs.map((a) =>
            a.tokens <= 0 ? null : (
              <path
                key={a.key}
                d={arcPath(cx, cy, r, a.start, a.end)}
                fill="none"
                stroke={a.color}
                strokeWidth={stroke}
                strokeLinecap="butt"
              />
            )
          )}
          <text x={cx} y={cy - 4} textAnchor="middle" className="usage-donut-center-value">
            {formatTokenCount(total)}
          </text>
          <text x={cx} y={cy + 14} textAnchor="middle" className="usage-donut-center-unit">
            tokens
          </text>
        </svg>
        <ul className="usage-donut-legend">
          {slices.map((s) => (
            <li key={s.key}>
              <span className="usage-dot" style={{ background: s.color }} />
              <div className="usage-donut-legend-text">
                <div className="usage-donut-legend-row">
                  <span className="usage-donut-name">{s.key}</span>
                  <span className="usage-donut-pct">{formatTokenPercent(s.tokens, total)}</span>
                </div>
                <span className="usage-donut-tokens">{formatTokenCount(s.tokens)} tokens</span>
              </div>
            </li>
          ))}
          {slices.length === 0 ? (
            <li className="usage-empty-hint">{t('usage:donut.empty')}</li>
          ) : null}
        </ul>
      </div>
    </div>
  );
}
