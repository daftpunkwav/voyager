/**
 * @file ArbiterBlock
 * @description Settings block for the chat arbiter mode (agent.arbiter.mode):
 * queue / auto / guide. Moved here from the chat topbar so all conversation
 * behavior knobs live in Settings -> Agent.
 *
 * Responsibilities:
 * - Load the current arbiter mode on mount
 * - Optimistically switch, confirm via a get_setting read-back, roll back and
 *   toast on failure
 *
 * Backend access goes through the capability bridge; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { GlassSelect } from '@/components/common/GlassSelect';
import { extractErrorMessage } from '@/utils/errors';

const ARBITER_KEY = 'agent.arbiter.mode';

/** Arbiter enum values (mirrors agent/settings.py choices). */
const ARBITER_OPTIONS = ['queue', 'auto', 'guide'] as const;

/** Chat arbiter mode (agent.arbiter.mode): how a new message is handled while the conversation is running */
export function ArbiterBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [arbiter, setArbiter] = useState<string | null>(null); // null = not loaded yet
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<{ value?: string; default?: string }>('settings', 'get_setting', {
      key: ARBITER_KEY,
    })
      .then((item) => {
        if (alive) setArbiter(item.value ?? item.default ?? 'queue');
      })
      .catch(() => {
        if (alive) setArbiter(''); // Read failed: disable the select instead of guessing a value
      });
    return () => {
      alive = false;
    };
  }, []);

  const changeArbiter = (value: string) => {
    if (busy || arbiter === null || arbiter === '') return;
    const prev = arbiter;
    setArbiter(value); // Optimistic update; roll back on failure
    setBusy(true);
    callCapability('settings', 'set_setting', { key: ARBITER_KEY, value })
      // After a successful set, read back via get_setting to confirm the persisted value
      .then(() =>
        callCapability<{ value?: string }>('settings', 'get_setting', { key: ARBITER_KEY })
      )
      .then((item) => {
        setArbiter(item.value ?? value);
        addToast({ type: 'success', message: t('arbiter.saved') });
      })
      .catch((err) => {
        setArbiter(prev);
        addToast({
          type: 'error',
          message: t('arbiter.switchFailed', { message: extractErrorMessage(err) }),
        });
      })
      .finally(() => setBusy(false));
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('arbiter.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('arbiter.desc')}
      </p>
      <div className="memory-form-row">
        <GlassSelect
          size="sm"
          value={arbiter ?? ''}
          aria-label={t('arbiter.title')}
          disabled={arbiter === null || arbiter === '' || busy}
          options={
            arbiter === null
              ? [{ value: '', label: t('arbiter.loading') }]
              : arbiter === ''
                ? [{ value: '', label: t('arbiter.loadFailed') }]
                : ARBITER_OPTIONS.map((o) => ({ value: o, label: t(`arbiter.${o}`) }))
          }
          onChange={changeArbiter}
        />
      </div>
    </div>
  );
}
