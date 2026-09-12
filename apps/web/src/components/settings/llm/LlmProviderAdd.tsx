/**
 * @file LlmProviderAdd
 * @description Add-provider form; presets come from llm.list_builtin_providers and creation goes through llm.add_provider.
 *
 * The API key is not entered here — it is configured on the detail card after adding.
 *
 * Responsibilities:
 * - Load builtin provider presets and prefill the form from a picked preset
 * - Create the provider through llm.add_provider and surface service errors
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import { addProvider, listBuiltinProviders } from '@/api/llm';
import type { LlmApiFormat, LlmBuiltinPreset } from '@/api/types';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';

interface LlmProviderAddProps {
  /** Called after a successful save with the new provider id (empty string = list refresh only) */
  onDone: (id: string) => void | Promise<void>;
}

export function LlmProviderAdd({ onDone }: LlmProviderAddProps) {
  const { t } = useTranslation('settings');
  const [presets, setPresets] = useState<LlmBuiltinPreset[]>([]);
  const [presetId, setPresetId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiFormat, setApiFormat] = useState<LlmApiFormat>('chat');
  const [modelsText, setModelsText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listBuiltinProviders()
      .then(setPresets)
      .catch((err) => setError((err as ServiceError).message));
  }, []);

  const applyPreset = (preset: LlmBuiltinPreset | undefined) => {
    setPresetId(preset?.preset_id ?? '');
    setDisplayName(preset?.display_name ?? '');
    setBaseUrl(preset?.base_url ?? '');
    setApiFormat(preset?.api_format ?? 'chat');
    setModelsText((preset?.models ?? []).join(', '));
  };

  const submit = async () => {
    setSaving(true);
    setError(null);
    try {
      const created = await addProvider({
        display_name: displayName.trim() || t('llm.add.unnamedName'),
        base_url: baseUrl.trim(),
        api_format: apiFormat,
        models: modelsText
          .split(/[,，\n]/)
          .map((m) => m.trim())
          .filter(Boolean),
        preset_id: presetId,
      });
      await onDone(created?.id ?? '');
    } catch (err) {
      const e = err as ServiceError;
      setError(e.hint ? `${e.message}(${e.hint})` : e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="provider-editor glass-card glass-card--overview-inner"
      style={{ marginBottom: 16 }}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="form-row">
        <label htmlFor="llm-add-preset">{t('llm.add.fromPreset')}</label>
        <select
          id="llm-add-preset"
          className="field input"
          value={presetId}
          onChange={(e) => applyPreset(presets.find((p) => e.target.value === p.preset_id))}
        >
          <option value="">{t('llm.add.custom')}</option>
          {presets.map((p) => (
            <option key={p.preset_id} value={p.preset_id}>
              {p.display_name}
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-name">{t('llm.add.displayName')}</label>
        <input
          id="llm-add-name"
          className="field input"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-url">Base URL</label>
        <input
          id="llm-add-url"
          className="field input"
          value={baseUrl}
          placeholder="https://api.example.com/v1"
          onChange={(e) => setBaseUrl(e.target.value)}
        />
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-format">{t('llm.provider.apiFormat')}</label>
        <select
          id="llm-add-format"
          className="field input"
          value={apiFormat}
          onChange={(e) => setApiFormat(e.target.value as LlmApiFormat)}
        >
          {LLM_API_FORMAT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {t(opt.labelKey)}({opt.hint})
            </option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label htmlFor="llm-add-models">{t('llm.add.modelsLabel')}</label>
        <textarea
          id="llm-add-models"
          className="field input"
          rows={2}
          value={modelsText}
          onChange={(e) => setModelsText(e.target.value)}
        />
      </div>
      {error ? <div className="setting-field__error small">{error}</div> : null}
      <div className="settings-actions llm-actions">
        <button type="submit" className="btn btn-primary" disabled={saving || !baseUrl.trim()}>
          {saving ? t('llm.add.saving') : t('llm.add.save')}
        </button>
      </div>
    </form>
  );
}
