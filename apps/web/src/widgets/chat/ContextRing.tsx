/**
 * @file ContextRing
 * @description Composer context-usage ring: polls agent.context_status for the
 * active session and renders a small SVG progress ring; clicking toggles a
 * popover with the detailed breakdown (window, used estimate vs provider
 * reported, resident memory cards, compact threshold, prefix-cache health).
 *
 * Errors degrade to a dimmed ring with a "no live context" popover — the ring
 * never blocks composing.
 */

import type { CSSProperties } from 'react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type ContextStatus, getContextStatus } from '@/api/agent';
import { useChatStore } from '@/stores/chatStore';
import { formatCompactCount } from '@/utils/trajectory';

const POLL_MS = 5000;

const RING_RADIUS = 8.5;
const RING_CIRC = 2 * Math.PI * RING_RADIUS;

export function ContextRing() {
  const { t } = useTranslation('chat');
  const sessionId = useChatStore((s) => s.activeSessionId);
  const [status, setStatus] = useState<ContextStatus | null>(null);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const pull = () => {
      getContextStatus(sessionId || undefined)
        .then((s) => {
          if (alive) setStatus(s);
        })
        .catch(() => {
          if (alive) setStatus(null); // no live context yet / session switched
        });
    };
    pull();
    const timer = setInterval(pull, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [sessionId]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const pct = status ? Math.min(100, Math.max(0, status.used_pct)) : 0;
  // Neutral until data exists; brand below the compact threshold, warning
  // between threshold and full, error when the window is nearly spent.
  const tone = !status
    ? 'var(--text-400)'
    : pct >= 95
      ? 'var(--error)'
      : pct >= status.auto_compact_at_pct
        ? 'var(--warning)'
        : 'var(--brand-500)';

  const rows = status
    ? [
        {
          k: t('chat:ctx.window'),
          v: t('chat:ctx.usedLine', {
            used: formatCompactCount(status.used_tokens),
            window: formatCompactCount(status.window_tokens),
            pct: Math.round(status.used_pct),
          }),
        },
        ...(typeof status.estimate_tokens === 'number'
          ? [{ k: t('chat:ctx.estimate'), v: `${formatCompactCount(status.estimate_tokens)}` }]
          : []),
        ...(typeof status.reported_tokens === 'number'
          ? [
              {
                k: t('chat:ctx.reported'),
                v: `${formatCompactCount(status.reported_tokens)}`,
              },
            ]
          : []),
        ...(typeof status.memory_cards_tokens === 'number'
          ? [
              {
                k: t('chat:ctx.memory'),
                v: `${formatCompactCount(status.memory_cards_tokens)}`,
              },
            ]
          : []),
        { k: t('chat:ctx.compact'), v: t('chat:ctx.pct', { pct: status.auto_compact_at_pct }) },
        ...(status.prefix_cache &&
        (status.prefix_cache.warm_rounds || status.prefix_cache.cold_rounds)
          ? [
              {
                k: t('chat:ctx.cache'),
                v: t('chat:ctx.cacheRounds', {
                  warm: status.prefix_cache.warm_rounds ?? 0,
                  cold: status.prefix_cache.cold_rounds ?? 0,
                }),
              },
            ]
          : []),
      ]
    : [];

  return (
    <div className="ctx-ring" ref={wrapRef}>
      <button
        type="button"
        className="ctx-ring__btn"
        aria-label={t('chat:ctx.aria')}
        title={t('chat:ctx.aria')}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <svg width={16} height={16} viewBox="0 0 24 24" aria-hidden>
          <circle
            cx="12"
            cy="12"
            r={RING_RADIUS}
            fill="none"
            stroke="var(--bg-300)"
            strokeWidth="2.5"
          />
          {status ? (
            <circle
              cx="12"
              cy="12"
              r={RING_RADIUS}
              fill="none"
              stroke={tone}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeDasharray={RING_CIRC}
              strokeDashoffset={RING_CIRC * (1 - pct / 100)}
              transform="rotate(-90 12 12)"
            />
          ) : null}
        </svg>
      </button>
      {open ? (
        <div className="ctx-ring__pop glass-card glass-card--dialog" role="dialog">
          <div className="ctx-ring__head">
            <strong>{t('chat:ctx.title')}</strong>
            <span className="muted">{t('chat:ctx.pct', { pct: Math.round(pct) })}</span>
          </div>
          {status ? (
            <>
              <ul className="ctx-ring__list">
                {rows.map((r) => (
                  <li key={r.k}>
                    <span className="ctx-ring__key">{r.k}</span>
                    <span className="ctx-ring__val">{r.v}</span>
                  </li>
                ))}
              </ul>
              <div className="ctx-ring__bar">
                <div
                  className="ctx-ring__fill"
                  style={{ '--fill': pct / 100, background: tone } as CSSProperties}
                />
                <div
                  className="ctx-ring__mark"
                  style={{ left: `${status.auto_compact_at_pct}%` }}
                  aria-hidden
                />
              </div>
            </>
          ) : (
            <p className="ctx-ring__empty small muted">{t('chat:ctx.empty')}</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
