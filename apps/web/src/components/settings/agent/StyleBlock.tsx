/**
 * @file StyleBlock
 * @description Settings block for the global speaking style (agent.style), a tone overlay applied on top of each agent's own temperament.
 *
 * Responsibilities:
 * - Load agent.style and offer preset values plus the raw custom value
 * - Save the selection and toast outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { STYLE_KEY, STYLE_PRESETS } from './constants';
import type { SettingItem } from './types';

/** Speaking style (agent.style): global tone overlay layered into every conversation's system prompt */
export function StyleBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [style, setStyle] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem>('settings', 'get_setting', { key: STYLE_KEY })
      .then((item) => {
        if (alive) setStyle(item.value ?? item.default ?? '热心');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveStyle = (value: string) => {
    const prev = style;
    setStyle(value);
    setSaving(true);
    callCapability<SettingItem>('settings', 'set_setting', { key: STYLE_KEY, value })
      .then((item) => {
        setStyle(item.value ?? value);
        addToast({ type: 'success', message: t('style.saved') });
      })
      .catch((err) => {
        setStyle(prev);
        addToast({
          type: 'error',
          message: t('style.saveFailed', { message: extractErrorMessage(err) }),
        });
      })
      .finally(() => setSaving(false));
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('style.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('style.desc')}
      </p>
      <GlassSelect
        size="sm"
        value={style ?? ''}
        options={
          loadFailed
            ? [{ value: '', label: t('style.loadFailedOption') }]
            : [
                // STYLE_PRESETS are backend-persisted values, so label === value (intentionally untranslated)
                ...STYLE_PRESETS.map((v) => ({ value: v, label: v })),
                ...(style && !STYLE_PRESETS.includes(style)
                  ? [{ value: style, label: style }]
                  : []),
              ]
        }
        onChange={(v) => saveStyle(v)}
        aria-label={t('style.aria')}
      />
      {saving && (
        <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
          {t('common.saving')}
        </span>
      )}
    </div>
  );
}
