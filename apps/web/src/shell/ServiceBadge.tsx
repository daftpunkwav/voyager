/**
 * @file ServiceBadge.tsx
 * @description Service badge strip: subscribes to service.health.changed and polls /health
 * initially; services that are down get a red dot.
 *
 * When /health is unreachable (backend not started) an "offline" badge is shown
 * with periodic retries instead of getting stuck in a loading state forever.
 *
 * Responsibilities:
 * - Poll /health on mount and render one up / down badge per service
 * - Subscribe to service.health.changed for live status flips
 * - Retry every 30s while unreachable; hide the strip when no services report
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchHealth } from '@/bridge/session';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';

interface ServiceState {
  [domain: string]: { status: string };
}

const RETRY_MS = 30_000;

export function ServiceBadges() {
  const { t } = useTranslation('shell');
  const [services, setServices] = useState<ServiceState>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const ac = new AbortController();
    const check = () => {
      fetchHealth(ac.signal)
        .then((body) => {
          if (!alive) return;
          setServices((body as { services?: ServiceState }).services ?? {});
          setLoaded(true);
        })
        .catch((err: unknown) => {
          if (!alive) return;
          if (err instanceof DOMException && err.name === 'AbortError') return;
          // Unreachable: mark the offline state and retry in 30s (the backend may be started later)
          setServices({});
          setLoaded(true);
          timer = setTimeout(check, RETRY_MS);
        });
    };
    check();

    const off = subscribe([EventType.SERVICE_HEALTH_CHANGED], (event) => {
      const { service, to } = event.payload as { service: string; to: string };
      setServices((prev) => ({ ...prev, [service]: { status: to } }));
    });
    return () => {
      alive = false;
      ac.abort();
      if (timer) clearTimeout(timer);
      off();
    };
  }, []);

  if (!loaded) {
    return (
      <div className="svc-strip">
        <div className="svc-badges" role="status" aria-label={t('svc.loadingAria')}>
          <span className="svc-badge svc-badge--loading" title={t('svc.checking')}>
            <span className="svc-badge__dot" aria-hidden />
            <span className="svc-badge__label">{t('svc.label')}</span>
          </span>
        </div>
      </div>
    );
  }

  if (Object.keys(services).length === 0) {
    // Pages already surface backend-unreachable errors/empty states themselves;
    // avoid duplicating that globally in the top strip.
    return null;
  }

  return (
    <div className="svc-strip">
      <div className="svc-badges" role="status" aria-label={t('svc.aria')}>
        {Object.entries(services).map(([domain, s]) => (
          <span
            key={domain}
            className={`svc-badge ${s.status === 'up' ? 'svc-badge--up' : 'svc-badge--down'}`}
            title={`${domain}: ${s.status}`}
          >
            <span className="svc-badge__dot" aria-hidden />
            {domain}
          </span>
        ))}
      </div>
    </div>
  );
}
