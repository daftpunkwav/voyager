/**
 * @file LlmProviderDetail
 * @description Provider detail card: metadata editing, API key save, model list management, enable/disable, and connection testing.
 *
 * Responsibilities:
 * - Edit provider display name, base URL and API format
 * - Save the API key without ever reading it back
 * - Manage the model list, enabled flag and connection tests
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmApiFormat, LlmModelMeta, LlmProvider, LlmTestOutcome } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { LlmModelEditDialog } from '@/components/settings/llm/LlmModelEditDialog';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';
import { GLASS_INNER } from '@/constants/glassTokens';

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
    fn().catch((err) => {
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
    run(() => onPatch(patch));
  };

  const saveKey = () => {
    const key = apiKeyDraft.trim();
    if (!key) return;
    setApiKeyDraft('');
    run(() => onSaveKey(key));
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

  return (
    <div
      className={`llm-provider-detail glass-card glass-card--overview-inner glass-overflow-visible`}
    >
      <div className="llm-provider-detail-head">
        <div className="llm-provider-detail-title-row">
          <h3 className="llm-block-title">{provider.display_name || t('llm.provider.unnamed')}</h3>
          {!isDefault ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={onSetDefault}>
              {t('llm.provider.setDefault')}
            </button>
          ) : (
            <span className="llm-provider-default-tag">{t('llm.provider.defaultTag')}</span>
          )}
        </div>
        <div className="llm-provider-enable-row">
          <button
            type="button"
            className={`llm-enable-pill ${provider.enabled ? 'is-on' : ''}`}
            onClick={() => !provider.enabled && run(() => onPatch({ enabled: true }))}
          >
            {t('llm.provider.enabled')}
          </button>
          <button
            type="button"
            className={`llm-enable-pill ${!provider.enabled ? 'is-off' : ''}`}
            onClick={() => provider.enabled && run(() => onPatch({ enabled: false }))}
          >
            {t('llm.provider.disable')}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm llm-provider-delete"
            onClick={onDelete}
            aria-label={t('llm.provider.deleteAria')}
          >
            {t('llm.provider.delete')}
          </button>
        </div>
      </div>

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
        <label htmlFor="llm-base-url">Base URL</label>
        <input
          id="llm-base-url"
          className="field input"
          value={urlDraft}
          onChange={(e) => setUrlDraft(e.target.value)}
          onBlur={commitBaseUrl}
          placeholder="https://…"
        />
      </div>

      <div className="form-row">
        <label>{t('llm.provider.apiFormat')}</label>
        <ul className={`llm-format-list ${GLASS_INNER}`}>
          {LLM_API_FORMAT_OPTIONS.map((opt) => {
            const selected = provider.api_format === opt.value;
            return (
              <li key={opt.value}>
                <button
                  type="button"
                  className={`llm-format-item ${selected ? 'is-selected' : ''}`}
                  onClick={() =>
                    !selected && run(() => onPatch({ api_format: opt.value as LlmApiFormat }))
                  }
                >
                  <span>
                    {t(opt.labelKey)}
                    <span className="muted"> {opt.hint}</span>
                  </span>
                  {selected ? <span aria-hidden>✓</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="form-row">
        <label htmlFor="llm-api-key">
          API Key
          <span className={`llm-key-masked ${provider.has_api_key ? '' : 'muted'}`}>
            {provider.has_api_key
              ? t('llm.provider.keySavedNote')
              : t('llm.provider.keyMissingNote')}
          </span>
        </label>
        <div className="llm-key-row">
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
            autoComplete="off"
          />
        </div>
        <div className="settings-actions llm-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!apiKeyDraft.trim()}
            onClick={saveKey}
          >
            {t('llm.provider.saveKey')}
          </button>
        </div>
      </div>

      <div className="form-row">
        <label htmlFor="llm-default-model">{t('llm.provider.defaultModel')}</label>
        <GlassSelect
          id="llm-default-model"
          value={provider.default_model}
          options={(provider.models.length
            ? provider.models
            : [provider.default_model].filter(Boolean)
          ).map((m) => ({ value: m, label: m }))}
          onChange={(v) => v !== provider.default_model && run(() => onPatch({ default_model: v }))}
          aria-label={t('llm.provider.defaultModel')}
        />
      </div>

      <div className="form-row">
        <label>{t('llm.provider.modelList')}</label>
        <ul className="llm-model-list">
          {provider.models.map((m) => {
            const meta = provider.models_meta?.[m];
            const badges: string[] = [];
            if (meta?.image_input) badges.push(t('llm.modelEdit.image'));
            if (meta?.audio_input) badges.push(t('llm.modelEdit.audio'));
            if (meta?.video_input) badges.push(t('llm.modelEdit.video'));
            if (meta?.thinking) badges.push(t('llm.modelEdit.thinkingBadge'));
            return (
              <li key={m} className={`llm-model-chip ${GLASS_INNER}`}>
                <button
                  type="button"
                  className="llm-model-chip__main"
                  title={t('llm.modelEdit.openAria', { model: m })}
                  onClick={() => setEditModel(m)}
                >
                  <span className="llm-model-chip__name">{m}</span>
                  {m === provider.default_model ? (
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
                  aria-label={t('llm.provider.removeModelAria', { model: m })}
                  onClick={() => removeModel(m)}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
        <div className="llm-model-add">
          <input
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
          />
          <button type="button" className="btn btn-ghost btn-sm" onClick={addModel}>
            {t('llm.provider.addModel')}
          </button>
        </div>
      </div>

      {editModel ? (
        <LlmModelEditDialog
          model={editModel}
          meta={provider.models_meta?.[editModel] ?? {}}
          onSave={(meta) => saveModelMeta(editModel, meta)}
          onClose={() => setEditModel(null)}
        />
      ) : null}

      <div className="llm-test-panel">
        <button
          type="button"
          className="btn btn-primary"
          disabled={isTesting || !activeModel || !provider.has_api_key}
          onClick={() => onTest(activeModel)}
          data-testid="test-llm-btn"
          title={provider.has_api_key ? undefined : t('llm.provider.testNeedsKey')}
        >
          {isTesting
            ? t('llm.provider.testing', { model: activeModel })
            : t('llm.provider.testBtn', { model: activeModel || t('llm.provider.noModel') })}
        </button>

        {testResult && (
          <div
            className={`llm-test-result ${testResult.ok ? 'llm-test-result--ok' : 'llm-test-result--fail'}`}
            role="status"
          >
            <div className="llm-test-result__head">
              <strong>
                {testResult.ok ? t('llm.provider.testOk') : t('llm.provider.testFail')}
              </strong>
              <span className="muted">
                {testResult.model ?? activeModel}
                {typeof testResult.latency_ms === 'number'
                  ? ` · ${formatLatency(testResult.latency_ms)}`
                  : ''}
              </span>
            </div>
            {!testResult.ok && (
              <pre className="llm-test-result__error">
                {testResult.error?.trim() || t('llm.provider.unknownError')}
              </pre>
            )}
          </div>
        )}

        {actionError ? (
          <div className="setting-field__error small" role="alert">
            {actionError}
          </div>
        ) : null}
      </div>
    </div>
  );
}
