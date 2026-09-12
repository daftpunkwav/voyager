/**
 * @file MemoryRetentionBlock
 * @description Settings block for episodic memory retention days (agent.memory.retention_days).
 *
 * Responsibilities:
 * - Load and save agent.memory.retention_days with an upper-bound check
 * - Toast invalid input and save outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { RETENTION_KEY, RETENTION_MAX } from './constants';
import type { SettingItem } from './types';

/** Episodic retention days (agent.memory.retention_days): standalone settings block split out of the memory viewer */
export function MemoryRetentionBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [retention, setRetention] = useState('');

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: RETENTION_KEY })
      .then((item) => {
        if (alive) setRetention(String(item.value ?? item.default ?? 0));
      })
      .catch(() => {
        /* Leave the draft empty on load failure; do not block the memory section */
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRetention = () => {
    const n = Number(retention);
    if (!Number.isInteger(n) || n < 0 || n > RETENTION_MAX) {
      addToast({ type: 'warning', message: t('retention.invalid', { max: RETENTION_MAX }) });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key: RETENTION_KEY, value: n })
      .then(() => {
        addToast({
          type: 'success',
          message: n > 0 ? t('retention.savedDays', { days: n }) : t('retention.savedManaged'),
        });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('retention.saveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('retention.title')}</h3>
      <div className="memory-form-row">
        <input
          className="field input"
          type="number"
          min={0}
          max={RETENTION_MAX}
          style={{ maxWidth: 120 }}
          value={retention}
          onChange={(e) => setRetention(e.target.value)}
          onBlur={saveRetention}
          aria-label={t('retention.aria')}
        />
        <button type="button" className="btn btn-sm btn-ghost" onClick={saveRetention}>
          {t('common.save')}
        </button>
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        {t('retention.desc')}
      </p>
    </div>
  );
}
