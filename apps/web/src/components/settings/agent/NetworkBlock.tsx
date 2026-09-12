/**
 * @file NetworkBlock
 * @description Settings block for network permissions (agent.network.*): access tier plus a domain whitelist.
 *
 * Responsibilities:
 * - Switch the network access tier and edit the domain whitelist draft
 * - Save both settings and toast outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { GlassSelect } from '@/components/common/GlassSelect';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { NETWORK_DOMAINS_KEY, NETWORK_MODE_KEY, NETWORK_MODE_OPTIONS } from './constants';
import type { SettingItem } from './types';

/** Network permissions (agent.network.*): access tier + whitelist domains; takes effect at the next network check */
export function NetworkBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [netMode, setNetMode] = useState<string | null>(null);
  const [domainsDraft, setDomainsDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: NETWORK_MODE_KEY })
      .then((item) => {
        if (alive) setNetMode(item.value ?? item.default ?? 'whitelist');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: NETWORK_DOMAINS_KEY })
      .then((item) => {
        if (alive) setDomainsDraft((item.value ?? item.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveNetworkMode = (mode: string) => {
    const prev = netMode;
    setNetMode(mode);
    callCapability<SettingItem<string>>('settings', 'set_setting', {
      key: NETWORK_MODE_KEY,
      value: mode,
    })
      .then(() => {
        addToast({ type: 'success', message: t('network.modeSaved') });
      })
      .catch((err) => {
        setNetMode(prev);
        addToast({
          type: 'error',
          message: t('network.modeSaveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  const saveDomains = () => {
    const lines = domainsDraft
      .split('\n')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    const bad = lines.find((line) => line.includes('://') || line.includes('/'));
    if (bad) {
      addToast({ type: 'warning', message: t('network.invalidDomain', { line: bad }) });
      return;
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', {
      key: NETWORK_DOMAINS_KEY,
      value: lines,
    })
      .then(() => {
        setDomainsDraft(lines.join('\n'));
        addToast({ type: 'success', message: t('network.domainsSaved', { count: lines.length }) });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('network.domainsSaveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  // Labels resolve at render time; unknown raw tier values pass through untranslated
  const modeOptions =
    netMode === null
      ? [{ value: '', label: t('network.loadingOption') }]
      : NETWORK_MODE_OPTIONS.some((o) => o.value === netMode)
        ? NETWORK_MODE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))
        : [
            ...NETWORK_MODE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) })),
            { value: netMode, label: netMode },
          ];

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('network.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('network.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <GlassSelect
            size="sm"
            value={netMode ?? ''}
            options={modeOptions}
            onChange={(v) => saveNetworkMode(v)}
            aria-label={t('network.modeAria')}
          />
          <p className="muted" style={{ fontSize: 12, margin: '8px 0 4px' }}>
            {t('network.domainsLabel')}
          </p>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={domainsDraft}
            disabled={netMode !== 'whitelist'}
            onChange={(e) => setDomainsDraft(e.target.value)}
            onBlur={saveDomains}
            placeholder={'github.com\narxiv.org'}
            aria-label={t('network.domainsAria')}
          />
          <div className="agent-guideline-meta">
            <span className="muted">
              {t('network.domainCount', {
                count: domainsDraft.split('\n').filter((s) => s.trim()).length,
              })}
            </span>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              disabled={netMode !== 'whitelist'}
              onClick={saveDomains}
            >
              {t('common.save')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
