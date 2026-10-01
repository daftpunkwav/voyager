/**
 * @file DynamicSettingsGroup
 * @description Schema-driven settings group: renders a filtered slice of the
 * settings registry (get_settings items carry type/min/max/choices/value) as
 * editable rows, so backend keys surface in the UI without a hand-written
 * block per key. This is the consumption half of the store's "dynamic
 * rendering" contract (see settingsStore).
 *
 * Responsibilities:
 * - Filter the shared schema (by module and/or key prefix, minus exclusions)
 * - Render one row per key: number / bool / choice / text / JSON / secret
 * - Save through set_setting; reload the shared schema afterwards
 *
 * Rows reuse the .settings-rows card grammar from the hand-written sections
 * (label left, control right) instead of a bespoke layout, so dynamic keys
 * read the same as the rest of the settings page.
 *
 * Labels resolve through settings:auto.<key> and fall back to the key's last
 * segment, so a new backend key is still usable before a label lands.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useSettingsStore } from '@/stores/settingsStore';
import { useUIStore } from '@/stores/uiStore';
import { GlassSelect } from '@/components/common/GlassSelect';
import { Switch } from '@/components/common/Switch';
import { extractErrorMessage } from '@/utils/errors';
import type { SettingSchemaItem } from '@/api/types';

/** Keys with a dedicated editing UI elsewhere; never duplicated here. */
export const DYNAMIC_EXCLUDE_DEFAULTS: ReadonlySet<string> = new Set([
  // Composed per model in the LLM settings section
  'agent.context.model_profiles',
  // Managed by McpBlock / PluginsBlock / ToolPermissions / AgentLlmOverridesPanel
  'agent.mcp.servers',
  'agent.plugins.approved',
  'agent.plugins.approvals',
  'agent.permissions',
  'agent.llm.overrides',
  'agent.style.overrides',
  // Owned by the composer picker / model settings / appearance section
  'llm.default_provider',
  'llm.default_model',
  'llm.reasoning_effort',
  'appearance.theme',
  'appearance.locale',
  'appearance.font_scale',
]);

interface GroupFilter {
  /** Include keys whose module is in this list. */
  modules?: string[];
  /** Include keys starting with one of these prefixes. */
  prefixes?: string[];
  /** Extra key blacklist on top of DYNAMIC_EXCLUDE_DEFAULTS. */
  exclude?: string[];
  /** i18n key for the group heading (h3). */
  titleKey?: string;
}

export function DynamicSettingsGroup({ modules, prefixes, exclude, titleKey }: GroupFilter) {
  const { t } = useTranslation('settings');
  const settings = useSettingsStore((s) => s.settings);
  const error = useSettingsStore((s) => s.error);

  const excluded = new Set([...DYNAMIC_EXCLUDE_DEFAULTS, ...(exclude ?? [])]);
  const items = (settings ?? []).filter((item) => {
    if (excluded.has(item.key)) return false;
    if (modules && modules.includes(item.module)) return true;
    if (prefixes && prefixes.some((p) => item.key.startsWith(p))) return true;
    return false;
  });
  // A filter that matches nothing renders nothing (the section may be
  // dedicated to other blocks); a failed schema load surfaces once per group.
  if (items.length === 0 && !error) return null;

  return (
    <div className="agent-settings-block">
      {titleKey && <h3 className="agent-settings-subtitle">{t(titleKey)}</h3>}
      {error && <p className="dynamic-settings__error">{t('common.loadFailed')}</p>}
      {!error &&
        // Only the first load renders nothing; a post-save reload keeps the
        // rows mounted on the stale schema so in-progress edits elsewhere
        // survive, and each row re-syncs when its persisted value changes.
        (settings ? (
          <div className="settings-rows dynamic-settings__rows">
            {items.map((item) => (
              <SettingRow key={item.key} item={item} />
            ))}
          </div>
        ) : null)}
    </div>
  );
}

/** label: settings:auto.<key> when present, else the key's last segment. */
function useRowLabel(key: string) {
  const { t } = useTranslation('settings');
  const translated = t(`auto.${key}`, { defaultValue: '' }) as string;
  return translated || key.split('.').slice(-1)[0];
}

function SettingRow({ item }: { item: SettingSchemaItem }) {
  const label = useRowLabel(item.key);
  if (item.secret) return <SecretRow item={item} label={label} />;
  if (item.type === 'bool') return <BoolRow item={item} label={label} />;
  if (item.type === 'choice') return <ChoiceRow item={item} label={label} />;
  return <ValueRow item={item} label={label} />;
}

/** Shared save path: set_setting, then refresh the shared schema so every
 *  row re-syncs from the persisted value. */
function useSettingSave() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const reload = useSettingsStore((s) => s.loadSettings);
  return (key: string, value: unknown, label: string) =>
    callCapability('settings', 'set_setting', { key, value })
      .then(() => {
        addToast({ type: 'success', message: t('auto.saved', { label }) });
        return reload();
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('auto.saveFailed', { label, message: extractErrorMessage(err) }),
        });
        throw err;
      });
}

function SecretRow({ item, label }: { item: SettingSchemaItem; label: string }) {
  const { t } = useTranslation('settings');
  return (
    <div className="settings-row">
      <span className="setting-row__label">{label}</span>
      <span className={`badge${item.has_value ? ' badge-success' : ''}`}>
        {item.has_value ? t('auto.secretSet') : t('auto.secretUnset')}
      </span>
    </div>
  );
}

function BoolRow({ item, label }: { item: SettingSchemaItem; label: string }) {
  const save = useSettingSave();
  const [busy, setBusy] = useState(false);
  const value = Boolean(item.value);
  return (
    <div className="settings-row">
      <span className="setting-row__label">{label}</span>
      <Switch
        checked={value}
        ariaLabel={label}
        disabled={busy}
        small
        onChange={(checked) => {
          setBusy(true);
          // useSettingSave already toasts the failure; only the busy gate
          // lives here, so the rethrown error is swallowed
          save(item.key, checked, label)
            .finally(() => setBusy(false))
            .catch(() => undefined);
        }}
      />
    </div>
  );
}

function ChoiceRow({ item, label }: { item: SettingSchemaItem; label: string }) {
  const save = useSettingSave();
  const [busy, setBusy] = useState(false);
  const value = String(item.value ?? '');
  return (
    <div className="settings-row">
      <span className="setting-row__label">{label}</span>
      <GlassSelect
        size="sm"
        aria-label={label}
        disabled={busy}
        value={value}
        options={item.choices.map((c) => ({ value: c, label: c }))}
        onChange={(next) => {
          setBusy(true);
          // Same as BoolRow: the toast is owned by useSettingSave
          save(item.key, next, label)
            .finally(() => setBusy(false))
            .catch(() => undefined);
        }}
      />
    </div>
  );
}

/** One editable value (int / float / str / json). The draft re-syncs whenever
 *  the shared schema reloads (after any save). */
function ValueRow({ item, label }: { item: SettingSchemaItem; label: string }) {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const save = useSettingSave();
  const numeric = item.type === 'int' || item.type === 'float';
  const wide = item.type === 'json';
  const [draft, setDraft] = useState(() => toDraft(item));
  // The draft handed to the last save attempt: the Save button and the
  // input's blur fire in sequence on a click, so without this guard every
  // button save would commit twice (duplicate request + duplicate toast).
  const lastCommitted = useRef<string | null>(null);
  // Re-sync only when the persisted serialization changes: the schema reload
  // after any row's save rebuilds every item object, and keying on the item
  // identity would clobber an in-progress edit in this row.
  const persisted = toDraft(item);
  useEffect(() => {
    setDraft(persisted);
  }, [persisted]);

  const commit = () => {
    if (draft === lastCommitted.current) return;
    if (numeric) {
      const n = Number(draft);
      if (
        draft.trim() === '' || // Number('') is 0: an emptied field must not save as zero
        !Number.isFinite(n) ||
        (item.min !== null && n < item.min) ||
        (item.max !== null && n > item.max)
      ) {
        addToast({ type: 'warning', message: t('auto.invalidRange', { label }) });
        return;
      }
      lastCommitted.current = draft;
      save(item.key, item.type === 'int' ? Math.round(n) : n, label).catch(() =>
        setDraft(toDraft(item))
      );
      return;
    }
    if (item.type === 'json') {
      try {
        const parsed = JSON.parse(draft);
        lastCommitted.current = draft;
        save(item.key, parsed, label).catch(() => setDraft(toDraft(item)));
      } catch {
        addToast({ type: 'warning', message: t('auto.invalidJson', { label }) });
      }
      return;
    }
    lastCommitted.current = draft;
    save(item.key, draft, label).catch(() => setDraft(toDraft(item)));
  };

  if (wide) {
    return (
      <div className="settings-row settings-row--stack">
        <span className="setting-row__label">{label}</span>
        <textarea
          className="field input setting-row__code"
          aria-label={label}
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
        />
        <div className="setting-row__actions">
          <button type="button" className="btn btn-sm btn-ghost" onClick={commit}>
            {t('common.save')}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="settings-row">
      <span className="setting-row__label">{label}</span>
      <div className="setting-row__control">
        <input
          className={`field input setting-row__input${numeric ? ' setting-row__input--num' : ''}`}
          type={numeric ? 'number' : 'text'}
          step={item.type === 'float' ? 'any' : undefined}
          min={item.min ?? undefined}
          max={item.max ?? undefined}
          aria-label={label}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
          }}
        />
        <button type="button" className="btn btn-sm btn-ghost" onClick={commit}>
          {t('common.save')}
        </button>
      </div>
    </div>
  );
}

function toDraft(item: SettingSchemaItem): string {
  const v = item.value;
  if (item.type === 'json') return JSON.stringify(v ?? null, null, 2);
  return v === null || v === undefined ? '' : String(v);
}
