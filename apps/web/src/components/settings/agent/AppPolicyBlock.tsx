/**
 * @file AppPolicyBlock
 * @description Settings block for the in-app capability allow/deny lists (agent.app.*).
 *
 * Responsibilities:
 * - Load and save the agent.app.* allow / deny lists as editable drafts
 * - Validate drafts before saving and toast load / save outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { APP_ALLOWED_KEY, APP_DENIED_KEY } from './constants';
import type { SettingItem } from './types';

/** In-app capability allow/deny lists (agent.app.*) */
export function AppPolicyBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [allowedDraft, setAllowedDraft] = useState('');
  const [deniedDraft, setDeniedDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    Promise.all([
      callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: APP_ALLOWED_KEY }),
      callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: APP_DENIED_KEY }),
    ])
      .then(([allowed, denied]) => {
        if (!alive) return;
        setAllowedDraft((allowed.value ?? allowed.default ?? ['*']).join('\n'));
        setDeniedDraft((denied.value ?? denied.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const parseLines = (raw: string) =>
    raw
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

  const validateLine = (line: string): string | null => {
    if (line === '*') return null;
    if (line.includes('://') || line.includes('/') || line.includes('\\')) {
      return t('appPolicy.errSeparator', { line });
    }
    if (line.includes('..')) return t('appPolicy.errDotDot', { line });
    if (line.includes(' ')) return t('appPolicy.errSpace', { line });
    if (/[A-Z]/.test(line)) return t('appPolicy.errUppercase', { line });
    if (!/^[a-z][a-z0-9_]*(?:\*?|__[a-z][a-z0-9_]*(?:\*?))$/.test(line)) {
      return t('appPolicy.errInvalidName', { line });
    }
    return null;
  };

  const save = (key: string, draft: string, labelKey: string, allowEmpty: boolean) => {
    const lines = parseLines(draft);
    if (!allowEmpty && lines.length === 0) {
      addToast({
        type: 'warning',
        message: t('appPolicy.emptyNotAllowed', { label: t(labelKey) }),
      });
      return;
    }
    for (const line of lines) {
      const err = validateLine(line);
      if (err) {
        addToast({ type: 'warning', message: err });
        return;
      }
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', { key, value: lines })
      .then(() => {
        if (key === APP_ALLOWED_KEY) setAllowedDraft(lines.join('\n'));
        else setDeniedDraft(lines.join('\n'));
        addToast({ type: 'success', message: t('appPolicy.saved', { label: t(labelKey) }) });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('appPolicy.saveFailed', {
            label: t(labelKey),
            message: extractErrorMessage(err),
          }),
        });
      });
  };

  const saveAllowed = () => save(APP_ALLOWED_KEY, allowedDraft, 'appPolicy.allowedLabel', false);
  const saveDenied = () => save(APP_DENIED_KEY, deniedDraft, 'appPolicy.deniedLabel', true);

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('appPolicy.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('appPolicy.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <p className="muted" style={{ fontSize: 12, margin: '8px 0 4px' }}>
            {t('appPolicy.allowedHeading')}
          </p>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={allowedDraft}
            onChange={(e) => setAllowedDraft(e.target.value)}
            onBlur={saveAllowed}
            placeholder={'*\nnotes__create_note'}
            aria-label={t('appPolicy.allowedLabel')}
          />
          <div className="agent-guideline-meta">
            <span className="muted">
              {t('appPolicy.entryCount', { count: parseLines(allowedDraft).length })}
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveAllowed}>
              {t('common.save')}
            </button>
          </div>

          <p className="muted" style={{ fontSize: 12, margin: '12px 0 4px' }}>
            {t('appPolicy.deniedHeading')}
          </p>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={deniedDraft}
            onChange={(e) => setDeniedDraft(e.target.value)}
            onBlur={saveDenied}
            placeholder={'notes__delete_note\ngraph__*'}
            aria-label={t('appPolicy.deniedLabel')}
          />
          <div className="agent-guideline-meta">
            <span className="muted">
              {t('appPolicy.entryCount', { count: parseLines(deniedDraft).length })}
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveDenied}>
              {t('common.save')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
