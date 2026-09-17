/**
 * @file UserHooksBlock
 * @description Settings block listing user hooks (declarative hook JSON files under workspace/hooks/) with a hot-reload action.
 *
 * Reload takes effect immediately without a restart; hooks from approved
 * plugins are unaffected by the reload.
 *
 * Responsibilities:
 * - List declarative hook files under workspace/hooks with their details
 * - Trigger hot reload and toast the applied load / unload results
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listUserHooks, reloadUserHooks } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { UserHookItem, UserHooksReloadResult } from './types';

/** User hooks: declarative hook JSON files under workspace/hooks/; after adding/editing/removing files, click reload for immediate effect (no restart); hooks from approved plugins are unaffected by reload. */
export function UserHooksBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [items, setItems] = useState<UserHookItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloading, setReloading] = useState(false); // busy flag against double submits

  const refresh = () =>
    listUserHooks<UserHookItem>()
      .then((items) => setItems(items))
      .catch(() => undefined); // Post-action refresh failure: keep the current list silently; toasts are the caller's job

  useEffect(() => {
    let alive = true;
    listUserHooks<UserHookItem>()
      .then((items) => {
        if (alive) setItems(items);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const onReload = async () => {
    if (reloading) return;
    setReloading(true);
    try {
      const res = await reloadUserHooks<UserHooksReloadResult>();
      let message = t('hooks.reloaded', { count: res.loaded });
      if (res.skipped && res.skipped.length > 0) {
        const detail = res.skipped.map((s) => `${s.path}（${s.reason}）`).join('、');
        message += t('hooks.skippedSuffix', { detail });
      }
      addToast({ type: 'success', message });
      await refresh();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('hooks.reloadFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setReloading(false);
    }
  };

  return (
    <div className="agent-settings-block">
      <div className="settings-group-head">
        <div className="settings-group-label">{t('hooks.title')}</div>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          aria-label={t('hooks.reloadAria')}
          disabled={reloading}
          onClick={() => void onReload()}
        >
          {reloading ? t('hooks.reloading') : t('hooks.reload')}
        </button>
      </div>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : items === null ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('hooks.loading')}
        </p>
      ) : items.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('hooks.empty', { example: '{ "on": "note.created", "enabled": true }' })}
        </p>
      ) : (
        <ul className="memory-entry-list">
          {items.map((h) => (
            <li key={h.path} className="memory-entry">
              <span className="memory-kind">{h.path}</span>
              <span className="memory-entry-summary">
                {h.on || t('hooks.unparsable')}
                {h.enabled ? '' : ` · ${t('hooks.disabled')}`}
                {h.loaded ? '' : ` · ${t('hooks.unloaded')}`}
              </span>
              <span className="muted" style={{ fontSize: 12 }}>
                {h.description}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
