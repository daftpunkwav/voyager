/**
 * @file LlmProviderDetail
 * @description Provider detail pane: identity header (name, format/host/key meta,
 * enable switch, default and delete actions) over hairline-separated groups —
 * provider fields, connection (URL / key) and the model list. Each model row
 * carries its own test / edit / delete actions plus an enabled switch; adding
 * a model opens the shared edit dialog in add mode. Flat by the single
 * top-layer glass principle: no nested card surface.
 *
 * Responsibilities:
 * - Edit provider display name, base URL and API format
 * - Save the API key without ever reading it back
 * - Manage the model list: add (dialog), edit (dialog), remove (confirmed),
 *   enable/disable and per-model connection tests
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmModelMeta, LlmProvider, LlmTestOutcome } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LlmModelEditDialog } from '@/components/settings/llm/LlmModelEditDialog';
import { LlmModelRowIcons } from '@/components/settings/llm/LlmModelRowIcons';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';

interface LlmProviderDetailProps {
  provider: LlmProvider;
  onPatch: (
    patch: Partial<
      Pick<
        LlmProvider,
        'display_name' | 'base_url' | 'api_format' | 'models' | 'models_meta' | 'enabled'
      >
    >
  ) => Promise<unknown>;
  onSaveKey: (key: string) => Promise<unknown>;
  onDelete: () => void;
  /** One real connection test for a single model; rejects with the backend error. */
  onTestModel: (model: string) => Promise<LlmTestOutcome>;
}

interface ModelDialogState {
  mode: 'edit' | 'add';
  id: string;
}

function formatLatency(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '-';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const sec = ms / 1000;
  return `${sec.toFixed(sec >= 10 ? 1 : 2)} s`;
}

/** Compact token budget badge: 200000 -> 200K, 1000000 -> 1M. */
function formatTokens(n?: number): string {
  if (!n || n <= 0) return '';
  const trim = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));
  if (n >= 1_000_000) return `${trim(n / 1_000_000)}M`;
  if (n >= 1_000) return `${trim(n / 1_000)}K`;
  return String(n);
}

type ProviderConfigModel = Record<string, unknown> & { id: string };

function modelToConfigDoc(id: string, meta: LlmModelMeta | undefined): ProviderConfigModel {
  const doc: Record<string, unknown> = { id };
  if (meta?.name) doc.name = meta.name;
  if (meta?.thinking) {
    const reasoning: Record<string, unknown> = { enabled: true };
    if (meta.thinking_variants?.length) reasoning.variants = meta.thinking_variants;
    if (meta.thinking_default) reasoning.defaultVariant = meta.thinking_default;
    doc.reasoning = reasoning;
  }
  const limit: Record<string, unknown> = {};
  if (meta?.context_window) limit.context = meta.context_window;
  if (meta?.max_output_tokens) limit.output = meta.max_output_tokens;
  if (Object.keys(limit).length) doc.limit = limit;
  const input = [
    'text',
    ...(meta?.image_input ? ['image'] : []),
    ...(meta?.audio_input ? ['audio'] : []),
    ...(meta?.video_input ? ['video'] : []),
  ];
  const output = meta?.output_modalities?.length ? meta.output_modalities : ['text'];
  doc.modalities = { input, output };
  if (meta?.compat && Object.keys(meta.compat).length) doc.compat = meta.compat;
  if (meta?.enabled === false) doc.enabled = false;
  return doc as ProviderConfigModel;
}

/** Whole-provider config file in the pi-agent shape; the api key is never
 *  read back, so it only appears if the user types it to rotate the key. */
function providerConfigJson(p: LlmProvider): string {
  const doc = {
    baseUrl: p.base_url,
    api: p.api_format,
    models: p.models.map((m) => modelToConfigDoc(m, p.models_meta?.[m])),
  };
  return JSON.stringify(doc, null, 2);
}

/** One config-doc model entry -> models_meta entry (undefined keys omitted). */
function configModelToMeta(m: Record<string, unknown>): LlmModelMeta {
  const meta: LlmModelMeta = {};
  if (typeof m.name === 'string' && m.name) meta.name = m.name;
  const reasoning =
    m.reasoning && typeof m.reasoning === 'object' && !Array.isArray(m.reasoning)
      ? (m.reasoning as Record<string, unknown>)
      : undefined;
  if (reasoning?.enabled === true) meta.thinking = true;
  if (Array.isArray(reasoning?.variants)) {
    meta.thinking_variants = (reasoning.variants as unknown[]).map(String).filter(Boolean);
  }
  if (typeof reasoning?.defaultVariant === 'string' && reasoning.defaultVariant) {
    meta.thinking_default = reasoning.defaultVariant;
  }
  const limit =
    m.limit && typeof m.limit === 'object' && !Array.isArray(m.limit)
      ? (m.limit as Record<string, unknown>)
      : undefined;
  if (typeof limit?.context === 'number' && limit.context > 0) {
    meta.context_window = Math.round(limit.context);
  }
  if (typeof limit?.output === 'number' && limit.output > 0) {
    meta.max_output_tokens = Math.round(limit.output);
  }
  const modalities =
    m.modalities && typeof m.modalities === 'object' && !Array.isArray(m.modalities)
      ? (m.modalities as Record<string, unknown>)
      : undefined;
  if (Array.isArray(modalities?.input)) {
    const input = (modalities.input as unknown[]).map(String);
    if (input.includes('image')) meta.image_input = true;
    if (input.includes('audio')) meta.audio_input = true;
    if (input.includes('video')) meta.video_input = true;
  }
  if (Array.isArray(modalities?.output)) {
    meta.output_modalities = (modalities.output as unknown[]).map(String).filter(Boolean);
  }
  if (m.compat && typeof m.compat === 'object' && !Array.isArray(m.compat)) {
    meta.compat = m.compat as Record<string, string | number | boolean | null>;
  }
  if (m.enabled === false) meta.enabled = false;
  return meta;
}

/** Host of the base URL for the identity meta line; raw string as fallback. */
function hostOf(baseUrl: string): string {
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl.replace(/^https?:\/\//, '').trim();
  }
}

export function LlmProviderDetail({
  provider,
  onPatch,
  onSaveKey,
  onDelete,
  onTestModel,
}: LlmProviderDetailProps) {
  const { t } = useTranslation('settings');
  const [nameDraft, setNameDraft] = useState(provider.display_name);
  const [urlDraft, setUrlDraft] = useState(provider.base_url);
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [keySaving, setKeySaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [modelDialog, setModelDialog] = useState<ModelDialogState | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [configOpen, setConfigOpen] = useState(false);
  const [configDraft, setConfigDraft] = useState('');
  const [configError, setConfigError] = useState<string | null>(null);
  const [configApplying, setConfigApplying] = useState(false);
  // Per-model test state: at most one request in flight, latest verdict per model
  const [testingModel, setTestingModel] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<string, LlmTestOutcome>>({});
  // Synchronous single-flight guard: React state updates are async, so two
  // clicks in the same tick would both see the stale state and double-fire.
  const testingRef = useRef(false);
  // API key: masked with 16 stars while untouched; typing schedules an
  // automatic overwrite (debounced, single-flight, flush on blur). The key
  // itself is never read back — the mask only signals "a key is stored".
  const keySaveTimer = useRef<number | null>(null);
  const keySavingRef = useRef(false);
  // Latest draft, readable inside async callbacks without stale closures.
  const latestKeyDraft = useRef('');
  const [keyFocused, setKeyFocused] = useState(false);
  const keyDisplay = apiKeyDraft || (!keyFocused && provider.has_api_key ? '*'.repeat(16) : '');

  const clearKeyTimer = () => {
    if (keySaveTimer.current !== null) {
      window.clearTimeout(keySaveTimer.current);
      keySaveTimer.current = null;
    }
  };

  // A pending debounced key save must not fire after the provider is switched
  useEffect(() => () => clearKeyTimer(), []);

  // Sync values coming back from the external reload into local drafts (after switching providers or remote changes)
  useEffect(() => {
    setNameDraft(provider.display_name);
  }, [provider.id, provider.display_name]);
  useEffect(() => {
    setUrlDraft(provider.base_url);
  }, [provider.id, provider.base_url]);

  const run = (fn: () => Promise<unknown>) => {
    setActionError(null);
    return fn().catch((err) => {
      const e = err as { message?: string; hint?: string };
      setActionError(
        e.hint ? `${e.message}(${e.hint})` : (e.message ?? t('llm.provider.actionFailed'))
      );
    });
  };

  const commitName = () => {
    const name = nameDraft.trim();
    if (!name || name === provider.display_name) return;
    run(() => onPatch({ display_name: name }));
  };

  const commitBaseUrl = () => {
    const url = urlDraft.trim();
    if (!url || url === provider.base_url) return;
    run(() => onPatch({ base_url: url }));
  };

  const saveKeyAuto = async (value: string) => {
    const key = value.trim();
    if (!key) return;
    if (keySavingRef.current) {
      // A save is in flight but the draft has moved on: re-run with the
      // latest value once it lands instead of silently dropping it.
      keySaveTimer.current = window.setTimeout(() => void saveKeyAuto(latestKeyDraft.current), 300);
      return;
    }
    keySavingRef.current = true;
    setKeySaving(true);
    try {
      await onSaveKey(key);
      setApiKeyDraft((cur) => (cur === value ? '' : cur));
    } catch (err) {
      const e = err as { message?: string; hint?: string };
      setActionError(
        e.hint ? `${e.message}(${e.hint})` : (e.message ?? t('llm.provider.actionFailed'))
      );
    } finally {
      keySavingRef.current = false;
      setKeySaving(false);
      // Edits made while the save was in flight were refused above — queue
      // them now so the stored key always converges to the latest input.
      if (latestKeyDraft.current.trim() && latestKeyDraft.current !== value) {
        keySaveTimer.current = window.setTimeout(
          () => void saveKeyAuto(latestKeyDraft.current),
          300
        );
      }
    }
  };

  const changeApiKey = (value: string) => {
    setApiKeyDraft(value);
    latestKeyDraft.current = value;
    clearKeyTimer();
    if (value.trim()) {
      keySaveTimer.current = window.setTimeout(() => void saveKeyAuto(value), 800);
    }
  };

  /** Mirror the model's token budgets into agent.context.model_profiles so the
   *  agent's context budget uses the real window without manual settings edits;
   *  clearing both budgets removes the profile. */
  const syncModelProfile = async (model: string, meta: LlmModelMeta) => {
    const profiles: Record<string, { window_tokens?: number; max_output_tokens?: number }> = {};
    try {
      const item = await callCapability<{ value?: unknown }>('settings', 'get_setting', {
        key: 'agent.context.model_profiles',
      });
      const v = item?.value;
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        Object.assign(profiles, v);
      }
    } catch {
      // unset key starts a fresh profile map
    }
    if (meta.context_window || meta.max_output_tokens) {
      profiles[model] = {
        window_tokens: meta.context_window ?? profiles[model]?.window_tokens,
        max_output_tokens: meta.max_output_tokens ?? profiles[model]?.max_output_tokens,
      };
    } else {
      delete profiles[model];
    }
    await callCapability('settings', 'set_setting', {
      key: 'agent.context.model_profiles',
      value: profiles,
    });
  };

  /** Dialog save: append the model in add mode (duplicate ids rejected), then
   *  merge the metadata and mirror the budgets. */
  const saveModel = async (model: string, meta: LlmModelMeta) => {
    const isNew = modelDialog?.mode === 'add';
    if (isNew && provider.models.includes(model)) {
      throw new Error(t('llm.modelEdit.duplicate', { model }));
    }
    const patch: Parameters<typeof onPatch>[0] = {
      models_meta: { ...(provider.models_meta ?? {}), [model]: meta },
    };
    if (isNew) {
      patch.models = [...provider.models, model];
    }
    await onPatch(patch);
    await syncModelProfile(model, meta);
    setModelDialog(null);
  };

  // run() surfaces a failed patch through actionError and keeps the confirm
  // dialog open (retry or cancel) instead of leaking an unhandled rejection.
  const removeModel = (model: string) => {
    const { [model]: _, ...metaRest } = provider.models_meta ?? {};
    return run(async () => {
      await onPatch({ models: provider.models.filter((m) => m !== model), models_meta: metaRest });
      try {
        await syncModelProfile(model, {});
      } catch {
        // profile cleanup must not block the removal (already patched)
      }
      setConfirmRemove(null);
    });
  };

  const toggleModel = (model: string, enabled: boolean) => {
    const meta = provider.models_meta?.[model] ?? {};
    return run(() =>
      onPatch({ models_meta: { ...(provider.models_meta ?? {}), [model]: { ...meta, enabled } } })
    );
  };

  const testModel = async (model: string) => {
    if (testingRef.current) return;
    testingRef.current = true;
    setTestingModel(model);
    try {
      const out = await onTestModel(model);
      setOutcomes((prev) => ({ ...prev, [model]: out }));
    } catch (err) {
      const e = err as { message?: string; hint?: string };
      setOutcomes((prev) => ({
        ...prev,
        [model]: {
          ok: false,
          error: e.hint ? `${e.message}(${e.hint})` : (e.message ?? t('llm.provider.unknownError')),
        },
      }));
    } finally {
      testingRef.current = false;
      setTestingModel(null);
    }
  };

  /** Apply the whole-provider config file: metadata patch, optional key
   *  rotation (apiKey field present), and budget mirroring per model. */
  const applyProviderConfig = async () => {
    if (configApplying) return;
    setConfigApplying(true);
    setConfigError(null);
    try {
      const doc = JSON.parse(configDraft) as Record<string, unknown>;
      if (typeof doc !== 'object' || doc === null || Array.isArray(doc)) {
        throw new Error('expected a JSON object');
      }
      const patch: Parameters<typeof onPatch>[0] = {};
      if (typeof doc.baseUrl === 'string' && doc.baseUrl.trim())
        patch.base_url = doc.baseUrl.trim();
      if (typeof doc.api === 'string' && doc.api.trim()) {
        patch.api_format = doc.api.trim() as typeof patch.api_format;
      }
      if (doc.models !== undefined) {
        if (!Array.isArray(doc.models)) throw new Error('"models" must be an array');
        const models: string[] = [];
        const meta: Record<string, LlmModelMeta> = {};
        for (const entry of doc.models) {
          if (
            typeof entry !== 'object' ||
            entry === null ||
            typeof entry.id !== 'string' ||
            !entry.id.trim()
          ) {
            throw new Error('every model needs a non-empty "id"');
          }
          const id = entry.id.trim();
          models.push(id);
          meta[id] = configModelToMeta(entry);
        }
        patch.models = models;
        patch.models_meta = meta;
      }
      await onPatch(patch);
      if (typeof doc.apiKey === 'string' && doc.apiKey.trim()) {
        await onSaveKey(doc.apiKey.trim());
      }
      // Mirror budgets for every model touched by the file
      if (patch.models_meta) {
        for (const [id, m] of Object.entries(patch.models_meta)) {
          await syncModelProfile(id, m);
        }
      }
      setConfigOpen(false);
    } catch (err) {
      setConfigError(
        `${t('llm.modelEdit.badJson')}: ${err instanceof Error ? err.message : String(err)}`
      );
    } finally {
      setConfigApplying(false);
    }
  };

  const formatLabel = t(
    LLM_API_FORMAT_OPTIONS.find((o) => o.value === provider.api_format)?.labelKey ??
      'settings:llm.format.chat'
  );

  return (
    <div className="llm-detail">
      <header className="llm-detail-head">
        <div className="llm-detail-heading">
          <div className="llm-detail-title-row">
            <h3 className="llm-detail-name">
              {provider.display_name || t('llm.provider.unnamed')}
            </h3>
          </div>
          <div className="llm-detail-meta">
            <span>{formatLabel}</span>
            <span aria-hidden>·</span>
            <span className="llm-detail-meta-host">{hostOf(provider.base_url) || '—'}</span>
            <span aria-hidden>·</span>
            <span className={provider.has_api_key ? '' : 'llm-detail-meta-warn'}>
              {provider.has_api_key ? t('llm.list.keySet') : t('llm.list.keyMissing')}
            </span>
          </div>
        </div>
        <div className="llm-detail-actions">
          <button
            type="button"
            role="switch"
            aria-checked={provider.enabled}
            aria-label={t('llm.provider.enableSwitchAria')}
            title={provider.enabled ? t('llm.provider.enabled') : t('llm.provider.disable')}
            className={`llm-switch ${provider.enabled ? 'is-on' : ''}`}
            onClick={() => run(() => onPatch({ enabled: !provider.enabled }))}
          >
            <span className="llm-switch__knob" />
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm llm-detail-delete"
            onClick={onDelete}
            aria-label={t('llm.provider.deleteAria')}
          >
            {t('llm.provider.delete')}
          </button>
        </div>
      </header>

      <section className="llm-group">
        <div className="llm-group-label">{t('llm.group.general')}</div>
        <div className="llm-form-grid">
          <div className="form-row">
            <label htmlFor="llm-display-name">{t('llm.provider.displayName')}</label>
            <input
              id="llm-display-name"
              className="field input"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onBlur={commitName}
            />
          </div>
          <div className="form-row">
            <label htmlFor="llm-api-format">{t('llm.provider.apiFormat')}</label>
            <GlassSelect
              id="llm-api-format"
              value={provider.api_format}
              options={LLM_API_FORMAT_OPTIONS.map((opt) => ({
                value: opt.value,
                label: `${t(opt.labelKey)}(${opt.hint})`,
              }))}
              onChange={(v) =>
                v !== provider.api_format &&
                run(() =>
                  onPatch({ api_format: v as (typeof LLM_API_FORMAT_OPTIONS)[number]['value'] })
                )
              }
              aria-label={t('llm.provider.apiFormat')}
            />
          </div>
        </div>
      </section>

      <section className="llm-group">
        <div className="llm-group-label">{t('llm.group.connection')}</div>
        <div className="form-row">
          <label htmlFor="llm-base-url">Base URL</label>
          <input
            id="llm-base-url"
            className="field input"
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            onBlur={commitBaseUrl}
            placeholder="https://…"
            spellCheck={false}
          />
        </div>
        <div className="form-row">
          <label htmlFor="llm-api-key">API Key</label>
          <div className="llm-key-field">
            <input
              id="llm-api-key"
              type="password"
              className="field input"
              placeholder={provider.has_api_key ? undefined : t('llm.provider.keyPlaceholder')}
              value={keyDisplay}
              onFocus={() => setKeyFocused(true)}
              onChange={(e) => changeApiKey(e.target.value)}
              onBlur={() => {
                setKeyFocused(false);
                clearKeyTimer();
                if (apiKeyDraft.trim()) void saveKeyAuto(apiKeyDraft);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  clearKeyTimer();
                  if (apiKeyDraft.trim()) void saveKeyAuto(apiKeyDraft);
                }
              }}
              autoComplete="off"
            />
            {keySaving ? (
              <span className="llm-key-saving" role="status">
                {t('llm.provider.keySaving')}
              </span>
            ) : null}
          </div>
        </div>
        {actionError ? (
          <div className="setting-field__error small" role="alert">
            {actionError}
          </div>
        ) : null}
      </section>

      <section className="llm-group">
        <div className="llm-group-head">
          <div className="llm-group-label">{t('llm.group.models')}</div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setModelDialog({ mode: 'add', id: '' })}
          >
            {t('llm.provider.addModel')}
          </button>
        </div>
        {provider.models.length === 0 ? (
          <p className="muted small llm-model-empty">{t('llm.modelList.empty')}</p>
        ) : (
          <ul className="llm-model-list">
            {provider.models.map((m) => {
              const meta = provider.models_meta?.[m];
              const enabled = meta?.enabled !== false;
              const outcome = outcomes[m];
              const testing = testingModel === m;
              const badges: string[] = [];
              if (meta?.image_input) badges.push(t('llm.modelEdit.image'));
              if (meta?.audio_input) badges.push(t('llm.modelEdit.audio'));
              if (meta?.video_input) badges.push(t('llm.modelEdit.video'));
              if (meta?.thinking) badges.push(t('llm.modelEdit.thinkingBadge'));
              const ctxBadge = formatTokens(meta?.context_window);
              return (
                <li key={m} className={`llm-model-row ${enabled ? '' : 'is-disabled'}`}>
                  <div className="llm-model-row__main">
                    <span className="llm-model-row__name" title={m}>
                      {meta?.name || m}
                    </span>
                    {ctxBadge ? (
                      <span
                        className="llm-model-row__badge"
                        title={t('llm.modelEdit.contextWindow')}
                      >
                        {ctxBadge}
                      </span>
                    ) : null}
                    {badges.map((b) => (
                      <span key={b} className="llm-model-row__badge">
                        {b}
                      </span>
                    ))}
                    {outcome?.ok ? (
                      <span className="llm-model-row__result is-ok" role="status">
                        {t('llm.provider.testOk')}
                        {typeof outcome.latency_ms === 'number'
                          ? ` · ${formatLatency(outcome.latency_ms)}`
                          : ''}
                      </span>
                    ) : null}
                    {outcome && !outcome.ok ? (
                      <span className="llm-model-row__result is-fail" role="status">
                        {t('llm.provider.testFail')}
                      </span>
                    ) : null}
                  </div>
                  <div className="llm-model-row__actions">
                    <button
                      type="button"
                      className="llm-icon-btn"
                      disabled={testingModel !== null || !provider.has_api_key}
                      title={
                        !provider.has_api_key
                          ? t('llm.provider.testNeedsKey')
                          : t('llm.modelList.testAria', { model: m })
                      }
                      aria-label={t('llm.modelList.testAria', { model: m })}
                      onClick={() => void testModel(m)}
                    >
                      {/* In-flight feedback lives on the button itself so the
                          row layout never shifts while testing */}
                      {testing ? (
                        <span className="llm-test-spinner" aria-hidden />
                      ) : (
                        <LlmModelRowIcons.test />
                      )}
                    </button>
                    <button
                      type="button"
                      className="llm-icon-btn"
                      title={t('llm.modelEdit.openAria', { model: m })}
                      aria-label={t('llm.modelEdit.openAria', { model: m })}
                      onClick={() => setModelDialog({ mode: 'edit', id: m })}
                    >
                      <LlmModelRowIcons.edit />
                    </button>
                    <button
                      type="button"
                      className="llm-icon-btn is-danger"
                      title={t('llm.provider.removeModelAria', { model: m })}
                      aria-label={t('llm.provider.removeModelAria', { model: m })}
                      onClick={() => setConfirmRemove(m)}
                    >
                      <LlmModelRowIcons.delete />
                    </button>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={enabled}
                      aria-label={t('llm.modelList.toggleAria', { model: m })}
                      title={enabled ? t('llm.provider.enabled') : t('llm.provider.disable')}
                      className={`llm-switch llm-switch--sm ${enabled ? 'is-on' : ''}`}
                      onClick={() => void toggleModel(m, !enabled)}
                    >
                      <span className="llm-switch__knob" />
                    </button>
                  </div>
                  {outcome && !outcome.ok && outcome.error ? (
                    <pre className="llm-test-result__error" role="status">
                      {outcome.error.trim() || t('llm.provider.unknownError')}
                    </pre>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="llm-group">
        <div className="llm-group-head">
          <div className="llm-group-label">{t('llm.provider.configFile')}</div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              if (!configOpen) setConfigDraft(providerConfigJson(provider));
              setConfigOpen(!configOpen);
            }}
          >
            {configOpen ? t('llm.provider.applyConfigCancel') : t('llm.provider.editConfig')}
          </button>
        </div>
        {configOpen ? (
          <div className="llm-config-block">
            <textarea
              className="llm-json-editor"
              value={configDraft}
              onChange={(e) => setConfigDraft(e.target.value)}
              rows={16}
              spellCheck={false}
              aria-label={t('llm.provider.configFile')}
            />
            <div className="llm-config-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={configApplying}
                onClick={() => void applyProviderConfig()}
              >
                {t('llm.provider.applyConfig')}
              </button>
            </div>
            {configError ? (
              <div className="setting-field__error small" role="alert">
                {configError}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      {modelDialog ? (
        <LlmModelEditDialog
          addMode={modelDialog.mode === 'add'}
          model={modelDialog.mode === 'edit' ? modelDialog.id : undefined}
          meta={modelDialog.mode === 'edit' ? provider.models_meta?.[modelDialog.id] : undefined}
          providerId={provider.id}
          onSave={(model, meta) => saveModel(model, meta)}
          onClose={() => setModelDialog(null)}
        />
      ) : null}

      <ConfirmDialog
        open={confirmRemove !== null}
        title={t('llm.modelList.removeTitle')}
        message={t('llm.modelList.removeConfirm', { model: confirmRemove ?? '' })}
        confirmLabel={t('llm.provider.removeModelAria', { model: confirmRemove ?? '' })}
        danger
        onConfirm={() => {
          if (confirmRemove) void removeModel(confirmRemove);
        }}
        onCancel={() => setConfirmRemove(null)}
      />
    </div>
  );
}
