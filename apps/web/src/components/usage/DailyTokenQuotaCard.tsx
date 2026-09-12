/**
 * @file DailyTokenQuotaCard
 * @description Today's token quota card backed by the agent process's in-process Meter.
 *
 * The meter resets on the UTC calendar day and counts input+output combined; this
 * differs in scope from the persisted "last N days" LLM history below. When
 * daily_tokens = 0 (unlimited) no progress bar is rendered.
 *
 * Responsibilities:
 * - Query the agent process's in-process token meter for today
 * - Render a progress bar that turns warning-colored near the cap
 * - Skip the progress bar entirely when the quota is unlimited
 */

import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getResourceQuota } from '@/api/agent';
import { backendUnreachable, extractErrorMessage } from '@/utils/errors';
import { GLASS_CHIP } from '@/constants/glassTokens';
import { formatTokenCount, formatTokenPercent } from '@/utils/formatTokens';

/** Warning threshold for approaching the cap: 90% counts as "near 100%" and turns the progress bar warning-colored */
const WARNING_RATIO = 0.9;

/** Today's token quota card: reads the agent process's in-process Meter for same-day usage,
 *  resetting on the UTC calendar day and counting input+output combined; scope differs
 *  from the persisted "last N days" history below. daily_tokens = 0 means unlimited, so no fake progress bar is drawn. */
export function DailyTokenQuotaCard() {
  const { t } = useTranslation('usage');
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['agent-daily-quota'],
    queryFn: () => getResourceQuota(),
  });

  const used = data?.tokens_used_today ?? 0;
  const limit = data?.daily_tokens ?? 0;
  const limited = limit > 0;
  const pct = limited ? Math.min(100, (used / limit) * 100) : 0;
  const isWarning = limited && used / limit >= WARNING_RATIO;

  return (
    <div className={`${GLASS_CHIP} usage-panel usage-quota`}>
      <div className="usage-quota-head">
        <h3 className="usage-panel-title">{t('usage:quota.title')}</h3>
        <span className="usage-quota-value" aria-label={t('usage:quota.usedAria')}>
          {/* Placeholder while data is loading: the default limit of 0 would misleadingly show "unlimited" */}
          {isLoading ? (
            '—'
          ) : (
            <>
              {t('usage:quota.used', { value: formatTokenCount(used) })}
              <span className="usage-quota-sep">·</span>
              {t('usage:quota.limit', {
                value: limited ? formatTokenCount(limit) : t('usage:quota.unlimited'),
              })}
            </>
          )}
        </span>
      </div>

      {isLoading && <p className="muted usage-quota-note">{t('usage:quota.loadingNote')}</p>}

      {isError && (
        <div className="usage-quota-error">
          <span className="muted usage-quota-note">
            {t('usage:quota.errorNote', {
              message: extractErrorMessage(error) || backendUnreachable(),
            })}
          </span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => void refetch()}>
            {t('common:action.retry')}
          </button>
        </div>
      )}

      {!isLoading && !isError && (
        <>
          {limited ? (
            <div
              className={`usage-quota-bar${isWarning ? ' is-warning' : ''}`}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(pct)}
              aria-label={t('usage:quota.barAria')}
            >
              <div className="usage-quota-bar-fill" style={{ width: `${pct}%` }} />
            </div>
          ) : null}
          <p className="muted usage-quota-note">
            {limited
              ? t('usage:quota.remaining', {
                  value: formatTokenCount(Math.max(0, limit - used)),
                  pct: formatTokenPercent(used, limit),
                })
              : t('usage:quota.noLimitNote')}
            {t('usage:quota.scopeNote')}
          </p>
        </>
      )}
    </div>
  );
}
