/**
 * @file LlmProviderAdd
 * @description Add-provider dialog rendered through the shared ModalOverlay;
 * presets come from llm.list_builtin_providers and creation goes through
 * llm.add_provider. The API key is not entered here — it is configured on the
 * detail pane after adding.
 *
 * Responsibilities:
 * - Load builtin provider presets and prefill the form from a picked preset chip
 * - Create the provider through llm.add_provider and surface service errors
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import { addProvider, listBuiltinProviders } from '@/api/llm';
import type { LlmApiFormat, LlmBuiltinPreset } from '@/api/types';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { LLM_API_FORMAT_OPTIONS } from '@/constants/llmConfig';

interface LlmProviderAddProps {
  open: boolean;
  onClose: () => void;
  /** Called after a successful save with the new provider id (empty string = list refresh only) */
  onDone: (id: string) => void | Promise<void>;
}

export function LlmProviderAdd({ open, onClose, onDone }: LlmProviderAddProps) {
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
    if (!open) return;
    listBuiltinProviders()
      .then(setPresets)
      .catch((err) => setError((err as ServiceError).message));
  }, [open]);

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
    <ModalOverlay open={open} onClose={onClose}>
      <form
        className="modal modal--wide glass-card--dialog llm-add-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('llm.add.title')}
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <h3 className="modal__title">{t('llm.add.title')}</h3>

        <div className="form-row">
          <label>{t('llm.add.fromPreset')}</label>
          <div className="llm-preset-row" role="radiogroup" aria-label={t('llm.add.fromPreset')}>
            <button
              type="button"
              role="radio"
              aria-checked={presetId === ''}
              className={`llm-preset-chip ${presetId === '' ? 'is-active' : ''}`}
              onClick={() => applyPreset(undefined)}
            >
              {t('llm.add.custom')}
            </button>
            {presets.map((p) => (
              <button
                key={p.preset_id}
                type="button"
                role="radio"
                aria-checked={presetId === p.preset_id}
                className={`llm-preset-chip ${presetId === p.preset_id ? 'is-active' : ''}`}
                onClick={() => applyPreset(p)}
              >
                {p.display_name}
              </button>
            ))}
          </div>
        </div>

        <div className="llm-form-grid">
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
            <label htmlFor="llm-add-format">{t('llm.provider.apiFormat')}</label>
            <GlassSelect
              id="llm-add-format"
              value={apiFormat}
              options={LLM_API_FORMAT_OPTIONS.map((opt) => ({
                value: opt.value,
                label: `${t(opt.labelKey)}(${opt.hint})`,
              }))}
              onChange={(v) => setApiFormat(v as LlmApiFormat)}
              aria-label={t('llm.provider.apiFormat')}
            />
          </div>
        </div>

        <div className="form-row">
          <label htmlFor="llm-add-url">Base URL</label>
          <input
            id="llm-add-url"
            className="field input"
            value={baseUrl}
            placeholder="https://api.example.com/v1"
            onChange={(e) => setBaseUrl(e.target.value)}
            spellCheck={false}
          />
        </div>

        <div className="form-row">
          <label htmlFor="llm-add-models">{t('llm.add.modelsLabel')}</label>
          <textarea
            id="llm-add-models"
            className="field input"
            rows={2}
            value={modelsText}
            onChange={(e) => setModelsText(e.target.value)}
            spellCheck={false}
          />
        </div>

        {error ? (
          <div className="setting-field__error small" role="alert">
            {error}
          </div>
        ) : null}

        <div className="modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t('llm.add.cancel')}
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || !baseUrl.trim()}>
            {saving ? t('llm.add.saving') : t('llm.add.create')}
          </button>
        </div>
      </form>
    </ModalOverlay>
  );
}
