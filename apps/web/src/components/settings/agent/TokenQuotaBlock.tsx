/**
 * @file TokenQuotaBlock
 * @description Settings block for the daily token quota (agent.resource.daily_tokens).
 *
 * Responsibilities:
 * - Load and save agent.resource.daily_tokens with an upper-bound check (0 = unlimited)
 * - Toast invalid input and save outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { DAILY_TOKENS_KEY, DAILY_TOKENS_MAX, numericDraft } from './constants';
import type { SettingItem } from './types';

/** Daily token quota (agent.resource.daily_tokens): caps the combined input+output tokens of all LLM calls within the UTC calendar day, 0 = unlimited; the backend hot-reads it before every complete */
export function TokenQuotaBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [quota, setQuota] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: DAILY_TOKENS_KEY })
      .then((item) => {
        if (alive) setQuota(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveQuota = () => {
    const n = Number(quota);
    // Empty strings (including whitespace-only) are not numbers and must be rejected explicitly: Number('') === 0 would fall into the valid domain and silently save 0 = unlimited
    // 0 is valid and means unlimited; everything else must be an integer in 1..max
    if (quota.trim() === '' || !Number.isInteger(n) || n < 0 || n > DAILY_TOKENS_MAX) {
      addToast({ type: 'warning', message: t('quota.invalid', { max: DAILY_TOKENS_MAX }) });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', {
      key: DAILY_TOKENS_KEY,
      value: n,
    })
      .then(() => {
        addToast({ type: 'success', message: t('quota.saved') });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('quota.saveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('quota.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('quota.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <div className="memory-form-row">
          <span className="muted" style={{ fontSize: 12 }}>
            {t('quota.dailyLabel')}
          </span>
          <input
            className="field input"
            type="number"
            min={0}
            max={DAILY_TOKENS_MAX}
            style={{ maxWidth: 120 }}
            value={quota}
            onChange={(e) => setQuota(e.target.value)}
            onBlur={saveQuota}
            aria-label={t('quota.title')}
          />
          <button type="button" className="btn btn-sm btn-ghost" onClick={saveQuota}>
            {t('common.save')}
          </button>
        </div>
      )}
    </div>
  );
}
