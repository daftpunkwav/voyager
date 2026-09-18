/**
 * @file UserHooksBlock
 * @description Settings "命令" section: declarative hook JSON files under
 * workspace/hooks/ rendered as command rows (path + trigger + description) in
 * the reference toolbar layout, with hot reload. Reload takes effect
 * immediately without a restart; hooks from approved plugins are unaffected.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listUserHooks, reloadUserHooks } from '@/api/agent';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import type { UserHookItem, UserHooksReloadResult } from './types';

export function UserHooksBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [items, setItems] = useState<UserHookItem[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [reloading, setReloading] = useState(false); // busy flag against double submits
  const [search, setSearch] = useState('');

  const refresh = () =>
    listUserHooks<UserHookItem>()
      .then((rows) => {
        setItems(rows);
        setLoadFailed(false);
      })
      .catch(() => undefined); // Post-action refresh failure: keep the current list silently; toasts are the caller's job

  useEffect(() => {
    let alive = true;
    listUserHooks<UserHookItem>()
      .then((rows) => {
        if (alive) setItems(rows);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items ?? [];
    return (items ?? []).filter(
      (h) =>
        h.path.toLowerCase().includes(q) ||
        (h.description ?? '').toLowerCase().includes(q) ||
        (h.on ?? '').toLowerCase().includes(q)
    );
  }, [items, search]);

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

  if (loadFailed) {
    return (
      <EmptyState
        title={t('hooks.loadFailedTitle')}
        description={t('common.loadFailed')}
        icon={EmptyStateIcons.warning}
        onRetry={() => void refresh()}
      />
    );
  }
  if (items === null) {
    return <LoadingSpinner label={t('hooks.loading')} />;
  }

  return (
    <div className="hooks-block">
      <SettingsToolbar
        countLabel={t('hooks.installed')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('hooks.searchPlaceholder')}
        actions={
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            aria-label={t('hooks.reloadAria')}
            disabled={reloading}
            onClick={() => void onReload()}
          >
            {reloading ? t('hooks.reloading') : t('hooks.reload')}
          </button>
        }
      />
      {filtered.length === 0 ? (
        items.length === 0 ? (
          <EmptyState
            title={t('hooks.emptyTitle')}
            description={t('hooks.empty', {
              example: '{ "on": "note.created", "enabled": true }',
            })}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <p className="muted small">{t('hooks.searchEmpty')}</p>
        )
      ) : (
        <ul className="settings-rows">
          {filtered.map((h) => (
            <li key={h.path} className="settings-row entity-row">
              <span className="entity-icon entity-icon--mono mono" aria-hidden>
                {'>_'}
              </span>
              <div className="entity-row__main">
                <span className="entity-row__title">
                  <span className="entity-row__name mono">{h.path}</span>
                  <span className="chip">{h.on || t('hooks.unparsable')}</span>
                  {h.enabled ? null : <span className="chip">{t('hooks.disabled')}</span>}
                  {h.loaded ? null : <span className="chip">{t('hooks.unloaded')}</span>}
                </span>
                {h.description && <span className="entity-row__desc">{h.description}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
