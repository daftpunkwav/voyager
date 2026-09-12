/**
 * @file MemoryBlock
 * @description Settings block for agent memory: profile summary and key-values, episodic/semantic/working zones, and zone clearing (retention days live in MemoryRetentionBlock).
 *
 * Responsibilities:
 * - Load the memory snapshot and edit the profile summary and key-values
 * - Clear zones and delete the profile behind confirmation dialogs
 * - Distinguish load failure from empty zones
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { clearMemory, deleteProfile, getMemory, setProfile } from '@/api/agent';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { fmtTs, fmtValue, ZONE_CONFIRM_KEYS, ZONE_LABEL_KEYS } from './constants';
import type { MemorySnapshot, MemoryZone } from './types';

/** Memory zones: summary / key-values / episodic / semantic / working / clearing (retention days split into MemoryRetentionBlock) */
export function MemoryBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [mem, setMem] = useState<MemorySnapshot | null>(null);
  const [memLoadFailed, setMemLoadFailed] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [confirmZone, setConfirmZone] = useState<MemoryZone | null>(null);
  const [busyZone, setBusyZone] = useState<MemoryZone | null>(null);

  const reload = () =>
    getMemory<MemorySnapshot>()
      .then((snap) => setMem(snap))
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('memory.refreshFailed', { message: extractErrorMessage(err) }),
        });
      });

  useEffect(() => {
    let alive = true;
    getMemory<MemorySnapshot>()
      .then((snap) => {
        if (!alive) return;
        setMem(snap);
      })
      .catch((err) => {
        if (!alive) return;
        setMemLoadFailed(true);
        addToast({
          type: 'error',
          message: t('memory.loadFailedToast', { message: extractErrorMessage(err) }),
        });
      });
    return () => {
      alive = false;
    };
  }, [addToast, t]);

  const addProfile = async () => {
    const key = newKey.trim();
    if (!key) {
      addToast({ type: 'warning', message: t('memory.keyRequired') });
      return;
    }
    try {
      await setProfile(key, newValue);
      setNewKey('');
      setNewValue('');
      addToast({ type: 'success', message: t('memory.profileSaved') });
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('memory.profileSaveFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  const removeProfile = async (key: string) => {
    try {
      await deleteProfile(key);
      addToast({ type: 'success', message: t('memory.profileDeleted', { key }) });
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('memory.profileDeleteFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  const clearWorking = async () => {
    setBusyZone('working');
    try {
      await clearMemory('working');
      addToast({ type: 'success', message: t('memory.workingCleared') });
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('memory.clearFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyZone(null);
    }
  };

  const clearZone = async () => {
    const zone = confirmZone;
    if (!zone || zone === 'working') return;
    try {
      await clearMemory(zone);
      addToast({
        type: 'success',
        message: t('memory.zoneCleared', { zone: t(ZONE_LABEL_KEYS[zone]) }),
      });
      await reload();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('memory.clearFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setConfirmZone(null);
    }
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('memory.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        {t('memory.desc')}
      </p>
      {memLoadFailed && (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('memory.loadFailed')}
        </p>
      )}
      {!memLoadFailed && !mem && (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('memory.loading')}
        </p>
      )}
      {mem && (
        <>
          <div className="memory-subhead">{t('memory.profileSummary')}</div>
          <pre className="memory-summary">{mem.profile.summary}</pre>

          <div className="memory-subhead">{t('memory.profileKv')}</div>
          {mem.profile.items.length === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>
              {t('memory.noProfileItems')}
            </p>
          ) : (
            <ul className="memory-kv-list">
              {mem.profile.items.map((item) => (
                <li key={item.key} className="memory-kv-row">
                  <span className="memory-kv-key">{item.key}</span>
                  <span className="memory-kv-value">{fmtValue(item.value)}</span>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={() => void removeProfile(item.key)}
                  >
                    {t('common.delete')}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="memory-form-row">
            <input
              className="field input"
              style={{ maxWidth: 180 }}
              placeholder={t('memory.keyPlaceholder')}
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              aria-label={t('memory.newKeyAria')}
            />
            <input
              className="field input"
              placeholder={t('memory.valuePlaceholder')}
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              aria-label={t('memory.newValueAria')}
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => void addProfile()}
            >
              {t('memory.add')}
            </button>
          </div>

          <div className="memory-subhead">
            {t('memory.episodicHeading', { count: mem.episodic.shown })}
          </div>
          {mem.episodic.shown === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>
              {t('memory.noEpisodic')}
            </p>
          ) : (
            <ul className="memory-entry-list">
              {mem.episodic.recent.map((e) => (
                <li key={e.id} className="memory-entry">
                  <time>{fmtTs(e.ts)}</time>
                  <span className="memory-kind">{e.kind}</span>
                  <span className="memory-entry-summary">{e.summary}</span>
                </li>
              ))}
            </ul>
          )}

          <div className="memory-subhead">
            {t('memory.semanticHeading', { count: mem.semantic.shown })}
          </div>
          {mem.semantic.shown === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>
              {t('memory.noSemantic')}
            </p>
          ) : (
            <ul className="memory-entry-list">
              {mem.semantic.recent.map((f) => (
                <li key={f.id} className="memory-entry">
                  <time>{fmtTs(f.ts)}</time>
                  <span className="memory-entry-summary">
                    {f.subject} · {f.relation} · {f.object}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="memory-subhead">{t(ZONE_LABEL_KEYS.working)}</div>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>
              {t('memory.workingMeta', { count: mem.working.size })}
            </span>
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() => void clearWorking()}
              disabled={busyZone === 'working'}
            >
              {t('memory.clear')}
            </button>
          </div>

          <div className="memory-subhead">{t('memory.clearHeading')}</div>
          <div className="memory-zone-grid">
            {(['profile', 'episodic', 'semantic'] as const).map((z) => (
              <button
                key={z}
                type="button"
                className="btn btn-sm btn-danger"
                onClick={() => setConfirmZone(z)}
              >
                {t('memory.clearZone', { zone: t(ZONE_LABEL_KEYS[z]) })}
              </button>
            ))}
            <button
              type="button"
              className="btn btn-sm btn-danger"
              onClick={() => setConfirmZone('all')}
              data-testid="clear-memory-all-btn"
            >
              {t('memory.clearAll')}
            </button>
          </div>
        </>
      )}

      {confirmZone && confirmZone !== 'working' && (
        <ConfirmDialog
          open
          title={t('memory.clearZone', { zone: t(ZONE_LABEL_KEYS[confirmZone]) })}
          message={t(ZONE_CONFIRM_KEYS[confirmZone])}
          confirmLabel={t('memory.clear')}
          danger
          onConfirm={() => void clearZone()}
          onCancel={() => setConfirmZone(null)}
        />
      )}
    </div>
  );
}
