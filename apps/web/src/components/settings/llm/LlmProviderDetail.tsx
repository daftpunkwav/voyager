/**
 * @file LlmProviderDetail
 * @description Provider detail pane: identity header (name, format/host/key meta,
 * enable switch, default and delete actions) over three hairline-separated
 * groups — provider fields, connection (URL / key / test), models.
 * Flat by the single top-layer glass principle: no nested card surface.
 *
 * Responsibilities:
 * - Edit provider display name, base URL and API format
 * - Save the API key without ever reading it back
 * - Manage the model list, enabled flag and connection tests
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmModelMeta, LlmProvider, LlmTestOutcome } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { LlmModelEditDialog } from '@/components/settings/llm/LlmModelEditDialog';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';

interface LlmProviderDetailProps {
  provider: LlmProvider;
  isDefault: boolean;
  isTesting: boolean;
  testResult: LlmTestOutcome | null;
  onPatch: (
    patch: Partial<
      Pick<
        LlmProvider,
        | 'display_name'
        | 'base_url'
        | 'api_format'
        | 'models'
        | 'models_meta'
        | 'default_model'
        | 'enabled'
      >
    >
  ) => Promise<unknown>;
  onSaveKey: (key: string) => Promise<unknown>;
  onSetDefault: () => void;
  onDelete: () => void;
  onTest: (model: string) => void;
}

function formatLatency(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '-';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const sec = ms / 1000;
  return `${sec.toFixed(sec >= 10 ? 1 : 2)} s`;
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
  isDefault,
  isTesting,
  testResult,
  onPatch,
  onSaveKey,
  onSetDefault,
  onDelete,
  onTest,
}: LlmProviderDetailProps) {
  const { t } = useTranslation('settings');
  const [nameDraft, setNameDraft] = useState(provider.display_name);
  const [urlDraft, setUrlDraft] = useState(provider.base_url);
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [keySaving, setKeySaving] = useState(false);
  const [newModel, setNewModel] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [editModel, setEditModel] = useState<string | null>(null);

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

  const addModel = () => {
    const name = newModel.trim();
    if (!name || provider.models.includes(name)) return;
    setNewModel('');
    run(() => onPatch({ models: [...provider.models, name] }));
  };

  const removeModel = (model: string) => {
    const next = provider.models.filter((m) => m !== model);
    const patch: Parameters<typeof onPatch>[0] = { models: next };
    if (provider.default_model === model) {
      patch.default_model = next[0] ?? '';
    }
    if (provider.models_meta && model in provider.models_meta) {
      const { [model]: _, ...rest } = provider.models_meta;
      patch.models_meta = rest;
    }
    run(() => onPatch(patch));
  };

  const saveKey = () => {
    const key = apiKeyDraft.trim();
    if (!key || keySaving) return;
    setApiKeyDraft('');
    setKeySaving(true);
    void run(() => onSaveKey(key)).finally(() => setKeySaving(false));
  };

  /** Mirror the model's token budgets into agent.context.model_profiles so the
   *  agent's context budget uses the real window without manual settings edits;
   *  clearing both budgets removes the profile. */
  const saveModelMeta = async (model: string, meta: LlmModelMeta) => {
    await onPatch({ models_meta: { ...(provider.models_meta ?? {}), [model]: meta } });
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
    setEditModel(null);
  };

  const activeModel = provider.default_model || provider.models[0] || '';
  const formatLabel = t(
    LLM_API_FORMAT_OPTIONS.find((o) => o.value === provider.api_format)?.labelKey ??
      'settings:llm.format.chat'
  );
  const modelOptions = (
    provider.models.length ? provider.models : [provider.default_model].filter(Boolean)
  ).map((m) => ({ value: m, label: m }));

  return (
    <div className="llm-detail">
      <header className="llm-detail-head">
        <div className="llm-detail-heading">
          <div className="llm-detail-title-row">
            <h3 className="llm-detail-name">
              {provider.display_name || t('llm.provider.unnamed')}
            </h3>
            {isDefault ? (
              <span className="llm-provider-default-tag">{t('llm.provider.defaultTag')}</span>
            ) : null}
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
          {!isDefault ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onSetDefault}>
              {t('llm.provider.setDefault')}
            </button>
          ) : null}
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
              placeholder={
                provider.has_api_key
                  ? t('llm.provider.keyOverwritePlaceholder')
                  : t('llm.provider.keyPlaceholder')
              }
              value={apiKeyDraft}
              onChange={(e) => setApiKeyDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  saveKey();
                }
              }}
              autoComplete="off"
            />
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!apiKeyDraft.trim() || keySaving}
              onClick={saveKey}
            >
              {t('llm.provider.saveKey')}
            </button>
          </div>
        </div>
        <div className="llm-test-row">
          <button
            type="button"
            className="btn btn-ghost llm-test-btn"
            disabled={isTesting || !activeModel || !provider.has_api_key}
            onClick={() => onTest(activeModel)}
            data-testid="test-llm-btn"
            title={provider.has_api_key ? undefined : t('llm.provider.testNeedsKey')}
          >
            {isTesting
              ? t('llm.provider.testing', { model: activeModel })
              : t('llm.provider.testBtn', { model: activeModel || t('llm.provider.noModel') })}
          </button>
          {testResult ? (
            <span
              className={`llm-test-verdict ${testResult.ok ? 'is-ok' : 'is-fail'}`}
              role="status"
            >
              {testResult.ok ? t('llm.provider.testOk') : t('llm.provider.testFail')}
              {typeof testResult.latency_ms === 'number'
                ? ` · ${formatLatency(testResult.latency_ms)}`
                : ''}
            </span>
          ) : null}
        </div>
        {testResult && !testResult.ok ? (
          <pre className="llm-test-result__error" role="status">
            {testResult.error?.trim() || t('llm.provider.unknownError')}
          </pre>
        ) : null}
        {actionError ? (
          <div className="setting-field__error small" role="alert">
            {actionError}
          </div>
        ) : null}
      </section>

      <section className="llm-group">
        <div className="llm-group-label">{t('llm.group.models')}</div>
        <div className="llm-form-grid">
          <div className="form-row">
            <label htmlFor="llm-default-model">{t('llm.provider.defaultModel')}</label>
            <GlassSelect
              id="llm-default-model"
              value={provider.default_model}
              options={modelOptions}
              onChange={(v) =>
                v !== provider.default_model && run(() => onPatch({ default_model: v }))
              }
              aria-label={t('llm.provider.defaultModel')}
            />
          </div>
        </div>
        <ul className="llm-model-list">
          {provider.models.map((m) => {
            const meta = provider.models_meta?.[m];
            const badges: string[] = [];
            if (meta?.image_input) badges.push(t('llm.modelEdit.image'));
            if (meta?.audio_input) badges.push(t('llm.modelEdit.audio'));
            if (meta?.video_input) badges.push(t('llm.modelEdit.video'));
            if (meta?.thinking) badges.push(t('llm.modelEdit.thinkingBadge'));
            const isDefaultModel = m === provider.default_model;
            return (
              <li key={m} className="llm-model-chip">
                <button
                  type="button"
                  className="llm-model-chip__main"
                  title={t('llm.modelEdit.openAria', { model: m })}
                  onClick={() => setEditModel(m)}
                >
                  {isDefaultModel ? <span className="llm-model-chip__dot" aria-hidden /> : null}
                  <span className="llm-model-chip__name">{m}</span>
                  {isDefaultModel ? (
                    <span className="llm-model-chip__default">{t('llm.provider.defaultTag')}</span>
                  ) : null}
                  {badges.map((b) => (
                    <span key={b} className="llm-model-chip__badge">
                      {b}
                    </span>
                  ))}
                </button>
                <button
                  type="button"
                  className="llm-model-chip__remove"
                  aria-label={t('llm.provider.removeModelAria', { model: m })}
                  onClick={() => removeModel(m)}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
        <div className="llm-key-field llm-model-add">
          <input
            id="llm-add-model"
            className="field input"
            placeholder={t('llm.provider.addModelPlaceholder')}
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addModel();
              }
            }}
            spellCheck={false}
            aria-label={t('llm.provider.addModel')}
          />
          <button type="button" className="btn btn-ghost btn-sm" onClick={addModel}>
            {t('llm.provider.addModel')}
          </button>
        </div>
      </section>

      {editModel ? (
        <LlmModelEditDialog
          model={editModel}
          meta={provider.models_meta?.[editModel] ?? {}}
          onSave={(meta) => saveModelMeta(editModel, meta)}
          onClose={() => setEditModel(null)}
        />
      ) : null}
    </div>
  );
}
