/**
 * @file ConductBlock
 * @description Settings block for the global conduct rules (agent.conduct), injected into every conversation's system prompt.
 *
 * Responsibilities:
 * - Load and save the free-form agent.conduct text under the length limit
 * - Track unsaved drafts and toast load / save outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { CONDUCT_KEY, CONDUCT_MAX } from './constants';
import type { SettingItem } from './types';

/** Global conduct rules (agent.conduct): apply to all agents, injected into every conversation's system prompt */
export function ConductBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [conductDraft, setConductDraft] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: CONDUCT_KEY })
      .then((item) => {
        if (!alive) return;
        const v = item.value ?? item.default ?? '';
        setConductDraft(v);
        setSaved(v);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveConduct = () => {
    if (saved === null) return;
    const next = conductDraft.slice(0, CONDUCT_MAX);
    if (next === saved) return;
    callCapability<SettingItem<string>>('settings', 'set_setting', {
      key: CONDUCT_KEY,
      value: next,
    })
      .then(() => {
        setSaved(next);
        addToast({ type: 'success', message: t('conduct.saved') });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('conduct.saveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('conduct.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('conduct.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <textarea
            className="field input agent-guideline-textarea"
            rows={5}
            maxLength={CONDUCT_MAX}
            value={conductDraft}
            onChange={(e) => setConductDraft(e.target.value)}
            onBlur={saveConduct}
            placeholder={t('conduct.placeholder')}
            aria-label={t('conduct.title')}
          />
          <div className="agent-guideline-meta">
            <span className="muted">
              {conductDraft.length}/{CONDUCT_MAX}
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveConduct}>
              {t('common.save')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
