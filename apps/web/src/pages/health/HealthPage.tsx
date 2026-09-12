/**
 * @file HealthPage
 * @description Service status page with live health polling, aggregated by the gateway /health endpoint.
 *
 * Fetches /health (per-service probes plus an overall status) on mount and
 * then every 15 seconds. Renders a status badge per service with the time of
 * its most recent status change.
 *
 * Responsibilities:
 * - Poll the aggregated /health payload on mount and every 15 seconds
 * - Render the overall status and a badge per service with its detail and
 *   last-probe time
 * - Show loading/error/empty states with a manual retry
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { fetchHealth as fetchHealthApi } from '@/bridge/session';
import { extractErrorMessage } from '@/utils/errors';

interface HealthRecord {
  service: string;
  status: 'up' | 'down' | 'degraded' | 'unknown';
  detail?: string;
  ts?: number;
}

interface HealthPayload {
  overall?: 'up' | 'down' | 'degraded' | 'unknown';
  services?: HealthRecord[];
}

export function HealthPage() {
  const { t } = useTranslation('health');
  const [payload, setPayload] = useState<HealthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const fetchHealth = async () => {
      try {
        const body = (await fetchHealthApi()) as HealthPayload;
        if (!alive) return;
        setPayload(body);
        setError(null);
      } catch (err) {
        if (alive) setError(extractErrorMessage(err));
      } finally {
        if (alive) setLoading(false);
      }
    };
    setLoading(true);
    void fetchHealth();
    const t = window.setInterval(fetchHealth, 15000);
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [retryTick]);

  return (
    <div className="health-page page-scaffold">
      {loading ? (
        <LoadingSpinner label={t('health:loading')} />
      ) : error ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('health:error.title')}
            description={error}
            icon={EmptyStateIcons.health}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      ) : !payload ? (
        <div className="page-scaffold__state">
          <EmptyState title={t('health:empty.title')} icon={EmptyStateIcons.health} />
        </div>
      ) : (
        <>
          <div className="page-scaffold__body">
            <GlassCard className={`health-overall health-overall--${payload.overall ?? 'unknown'}`}>
              <span className="label">{t('health:overall')}</span>
              <span className="value">{payload.overall ?? 'unknown'}</span>
            </GlassCard>
            <h2 className="h3">{t('health:services')}</h2>
            <div className="health-grid">
              {(payload.services ?? []).map((s) => (
                <GlassCard key={s.service} className={`health-card health-card--${s.status}`}>
                  <div className="health-card__head">
                    <span className="health-card__name mono">{s.service}</span>
                    <span className={`chip health-chip--${s.status}`}>{s.status}</span>
                  </div>
                  {s.detail ? <p className="muted small">{s.detail}</p> : null}
                  {s.ts ? (
                    <p className="small mono">
                      {t('health:lastProbe', { time: new Date(s.ts * 1000).toLocaleString() })}
                    </p>
                  ) : null}
                </GlassCard>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default HealthPage;
