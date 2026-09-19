/**
 * @file ToolPermissions
 * @description Settings "工具权限" section: the agent tool permission policy
 * (agent.permissions) — one mode plus deny/allow lists, default full.
 *
 * - Mode cards: full / no_dangerous / read_only, current one highlighted
 * - Tool table: one row per roster tool with its class badge (R read-only /
 *   D dangerous, unknown tools read as D) and one-click add-to-list actions;
 *   the allow actions are unavailable in read_only (hard ceiling, no allow)
 * - Editable deny/allow lists: entries are "tool", "tool.action" or
 *   "bash:<command prefix>"; removing is one click, adding is a free-text row
 *
 * Values are written straight through set_setting (user_only backend key) and
 * take effect on the agent's next tool call — the resolver hot-reads.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { listTools } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import type { SettingItem } from '@/components/settings/agent/types';
import type { ToolItem } from '@/components/team/types';

const PERMISSIONS_KEY = 'agent.permissions';

type PermMode = 'full' | 'no_dangerous' | 'read_only';

interface PermConfig {
  mode: PermMode;
  deny: string[];
  allow: string[];
}

const MODES: PermMode[] = ['full', 'no_dangerous', 'read_only'];

function normalizeConfig(raw: unknown): PermConfig {
  const obj = (raw ?? {}) as Record<string, unknown>;
  const mode = MODES.includes(obj.mode as PermMode) ? (obj.mode as PermMode) : 'full';
  const list = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((e): e is string => typeof e === 'string' && e.length > 0) : [];
  return { mode, deny: list(obj.deny), allow: list(obj.allow) };
}

export function ToolPermissions() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [tools, setTools] = useState<ToolItem[] | null>(null);
  const [config, setConfig] = useState<PermConfig | null>(null);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([
      listTools<ToolItem>(),
      callCapability<SettingItem<PermConfig>>('settings', 'get_setting', { key: PERMISSIONS_KEY }),
    ])
      .then(([roster, item]) => {
        if (!alive) return;
        setTools(Array.isArray(roster) ? roster : []);
        setConfig(normalizeConfig(item.value ?? item.default));
      })
      .catch((err) => {
        if (alive) setLoadError(extractErrorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, []);

  const save = async (next: PermConfig, okKey: string) => {
    try {
      await callCapability('settings', 'set_setting', { key: PERMISSIONS_KEY, value: next });
      setConfig(next);
      addToast({ type: 'success', message: t(okKey) });
    } catch (err) {
      addToast({
        type: 'error',
        message: t('toolPerms.saveFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  const toggleListEntry = (list: 'deny' | 'allow', entry: string) => {
    if (!config) return;
    const has = config[list].includes(entry);
    const nextList = has ? config[list].filter((e) => e !== entry) : [...config[list], entry];
    void save({ ...config, [list]: nextList }, 'toolPerms.saved');
  };

  const addEntry = (list: 'deny' | 'allow') => {
    if (!config) return;
    const entry = draft.trim();
    if (!entry) return;
    if (config.deny.includes(entry) || config.allow.includes(entry)) {
      addToast({ type: 'warning', message: t('toolPerms.duplicate') });
      return;
    }
    setDraft('');
    void save({ ...config, [list]: [...config[list], entry] }, 'toolPerms.saved');
  };

  // A tool row is highlighted when the tool (or one of its action entries) is
  // explicitly listed; entries that mention no roster tool (bash: prefixes,
  // action entries) still show in the lists below.
  const listedTools = useMemo(() => {
    if (!config) return { deny: new Set<string>(), allow: new Set<string>() };
    const names = new Set((tools ?? []).map((tl) => tl.name));
    const pick = (list: string[]) => {
      const s = new Set<string>();
      for (const e of list) if (names.has(e)) s.add(e);
      return s;
    };
    return { deny: pick(config.deny), allow: pick(config.allow) };
  }, [config, tools]);

  if (tools === null && !loadError) {
    return <LoadingSpinner label={t('toolPerms.loading')} />;
  }
  if (loadError) {
    return (
      <EmptyState
        title={t('toolPerms.loadFailed')}
        description={loadError}
        icon={EmptyStateIcons.warning}
      />
    );
  }
  if (!config) return null;

  const readOnly = config.mode === 'read_only';

  return (
    <div className="tool-perms">
      <div className="settings-group">
        <div className="settings-group-label">{t('toolPerms.modeLabel')}</div>
        <div className="chips tool-perms__modes">
          {MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              className={`chip${config.mode === mode ? ' active' : ''}`}
              onClick={() => void save({ ...config, mode }, 'toolPerms.saved')}
            >
              {t(`toolPerms.mode.${mode}`)}
            </button>
          ))}
        </div>
        <p className="muted small tool-perms__mode-hint">
          {t(`toolPerms.modeHint.${config.mode}`)}
        </p>
      </div>

      <div className="settings-group">
        <div className="settings-group-label">
          {t('toolPerms.tableLabel')}
          <span className="tools-catalog__group-count">
            {t('tools.groupCount', { n: tools?.length ?? 0 })}
          </span>
        </div>
        <ul className="settings-rows">
          {(tools ?? []).map((tool) => {
            const denied = listedTools.deny.has(tool.name);
            const allowed = listedTools.allow.has(tool.name);
            return (
              <li key={tool.name} className="settings-row tool-perms__row">
                <span className="entity-row__title">
                  <code className="mono entity-row__name">{tool.name}</code>
                  <span className={`chip${tool.class === 'D' ? ' chip--danger' : ''}`}>
                    {tool.class === 'D' ? t('toolPerms.classD') : t('toolPerms.classR')}
                  </span>
                </span>
                <span className="tool-perms__actions">
                  <button
                    type="button"
                    className={`btn btn-sm${denied ? ' btn-ghost' : ''}`}
                    onClick={() => toggleListEntry('deny', tool.name)}
                  >
                    {denied ? t('toolPerms.removeDeny') : t('toolPerms.addDeny')}
                  </button>
                  <button
                    type="button"
                    className={`btn btn-sm${allowed ? ' btn-ghost' : ''}`}
                    disabled={readOnly && !allowed}
                    title={readOnly ? t('toolPerms.allowDisabledHint') : undefined}
                    onClick={() => toggleListEntry('allow', tool.name)}
                  >
                    {allowed ? t('toolPerms.removeAllow') : t('toolPerms.addAllow')}
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {(['deny', 'allow'] as const).map((list) => (
        <div key={list} className="settings-group">
          <div className="settings-group-label">{t(`toolPerms.listLabel.${list}`)}</div>
          <ul className="settings-rows">
            {config[list].length === 0 ? (
              <li className="settings-row muted small">{t(`toolPerms.listEmpty.${list}`)}</li>
            ) : (
              config[list].map((entry) => (
                <li key={entry} className="settings-row tool-perms__entry">
                  <code className="mono">{entry}</code>
                  <button
                    type="button"
                    className="btn btn-sm btn-ghost"
                    onClick={() => toggleListEntry(list, entry)}
                  >
                    {t('toolPerms.remove')}
                  </button>
                </li>
              ))
            )}
          </ul>
          <div className="tool-perms__add">
            <input
              className="field input"
              value={draft}
              placeholder={t('toolPerms.addPlaceholder')}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  addEntry(list);
                }
              }}
            />
            <button type="button" className="btn btn-sm" onClick={() => addEntry(list)}>
              {t('toolPerms.add')}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
