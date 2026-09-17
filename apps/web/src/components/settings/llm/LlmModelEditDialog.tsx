/**
 * @file LlmModelEditDialog
 * @description Per-model configuration dialog (llm settings). The JSON config
 * file is the single source of truth, shaped like the ZCode provider config:
 * reasoning { enabled, variants, defaultVariant }, limit { context, output },
 * modalities { input, output }. GUI controls are projections of it, and
 * editing the JSON directly wins on save. In add mode the id can be picked
 * from the provider's live model catalog (GET /models) instead of free-typing.
 * Shell is the shared ModalOverlay (portal + scrim + enter/exit animation).
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LlmModelMeta } from '@/api/types';
import { listRemoteModels } from '@/api/llm';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface LlmModelEditDialogProps {
  /** Model id in edit mode (displayed read-only in the id field). */
  model?: string;
  /** Current metadata in edit mode; add mode starts from a blank form. */
  meta?: LlmModelMeta;
  addMode?: boolean;
  /** Provider id for the live catalog picker (add mode). */
  providerId?: string;
  onSave: (model: string, meta: LlmModelMeta) => Promise<void>;
  onClose: () => void;
}

interface ModelForm {
  id: string;
  name: string;
  image: boolean;
  audio: boolean;
  video: boolean;
  thinking: boolean;
  /** Supported thinking variants, comma separated ("low, high, max"). */
  variants: string;
  /** Default thinking variant (one of the variants when set). */
  defaultVariant: string;
  contextWindow: string;
  maxOutput: string;
  /** Output modalities, comma separated ("text"). */
  outputModalities: string;
  compat: Record<string, string | number | boolean | null> | undefined;
  json: string;
}

const splitList = (raw: string): string[] =>
  raw
    .split(/[,，\n]/)
    .map((x) => x.trim())
    .filter(Boolean);

function buildJson(f: Omit<ModelForm, 'json'>): string {
  const doc: Record<string, unknown> = {};
  if (f.name.trim()) doc.name = f.name.trim();
  if (f.thinking) {
    const reasoning: Record<string, unknown> = { enabled: true };
    const variants = splitList(f.variants);
    if (variants.length) reasoning.variants = variants;
    if (f.defaultVariant.trim()) reasoning.defaultVariant = f.defaultVariant.trim();
    doc.reasoning = reasoning;
  }
  const limit: Record<string, unknown> = {};
  const win = Number(f.contextWindow);
  if (f.contextWindow.trim() && Number.isFinite(win) && win > 0) limit.context = Math.round(win);
  const out = Number(f.maxOutput);
  if (f.maxOutput.trim() && Number.isFinite(out) && out > 0) limit.output = Math.round(out);
  if (Object.keys(limit).length) doc.limit = limit;
  const input = [
    'text',
    ...(f.image ? ['image'] : []),
    ...(f.audio ? ['audio'] : []),
    ...(f.video ? ['video'] : []),
  ];
  const output = splitList(f.outputModalities);
  doc.modalities = { input, output: output.length ? output : ['text'] };
  if (f.compat && Object.keys(f.compat).length) doc.compat = f.compat;
  return JSON.stringify(doc, null, 2);
}

/** Parse the JSON config into form state; throws on malformed input. */
function jsonToForm(json: string, base: ModelForm): ModelForm {
  const doc = JSON.parse(json) as Record<string, unknown>;
  if (typeof doc !== 'object' || doc === null || Array.isArray(doc)) {
    throw new Error('expected a JSON object');
  }
  const reasoning =
    doc.reasoning && typeof doc.reasoning === 'object' && !Array.isArray(doc.reasoning)
      ? (doc.reasoning as Record<string, unknown>)
      : undefined;
  const limit =
    doc.limit && typeof doc.limit === 'object' && !Array.isArray(doc.limit)
      ? (doc.limit as Record<string, unknown>)
      : undefined;
  const modalities =
    doc.modalities && typeof doc.modalities === 'object' && !Array.isArray(doc.modalities)
      ? (doc.modalities as Record<string, unknown>)
      : undefined;
  const input = Array.isArray(modalities?.input) ? (modalities.input as unknown[]).map(String) : [];
  const compat = doc.compat;
  if (
    compat !== undefined &&
    (typeof compat !== 'object' || compat === null || Array.isArray(compat))
  ) {
    throw new Error('"compat" must be an object');
  }
  const outputModalities = Array.isArray(modalities?.output)
    ? (modalities.output as unknown[]).map(String).join(', ')
    : base.outputModalities;
  return {
    id: base.id,
    name: typeof doc.name === 'string' ? doc.name : '',
    image: input.includes('image'),
    audio: input.includes('audio'),
    video: input.includes('video'),
    thinking: reasoning?.enabled === true,
    variants: Array.isArray(reasoning?.variants)
      ? (reasoning.variants as unknown[]).map(String).join(', ')
      : '',
    defaultVariant: typeof reasoning?.defaultVariant === 'string' ? reasoning.defaultVariant : '',
    contextWindow: typeof limit?.context === 'number' ? String(limit.context) : '',
    maxOutput: typeof limit?.output === 'number' ? String(limit.output) : '',
    outputModalities,
    compat: compat as ModelForm['compat'],
    json: JSON.stringify(doc, null, 2),
  };
}

function formToMeta(f: ModelForm): LlmModelMeta {
  const meta: LlmModelMeta = {
    image_input: f.image,
    audio_input: f.audio,
    video_input: f.video,
    thinking: f.thinking,
  };
  if (f.name.trim()) meta.name = f.name.trim();
  const variants = splitList(f.variants);
  if (f.thinking && variants.length) meta.thinking_variants = variants;
  if (f.thinking && f.defaultVariant.trim()) meta.thinking_default = f.defaultVariant.trim();
  const win = Number(f.contextWindow);
  if (f.contextWindow.trim() && Number.isFinite(win) && win > 0) {
    meta.context_window = Math.round(win);
  }
  const out = Number(f.maxOutput);
  if (f.maxOutput.trim() && Number.isFinite(out) && out > 0)
    meta.max_output_tokens = Math.round(out);
  const output = splitList(f.outputModalities);
  if (output.length) meta.output_modalities = output;
  if (f.compat && Object.keys(f.compat).length) meta.compat = f.compat;
  return meta;
}

export function LlmModelEditDialog({
  model = '',
  meta,
  addMode = false,
  providerId,
  onSave,
  onClose,
}: LlmModelEditDialogProps) {
  const { t } = useTranslation('settings');
  const [form, setForm] = useState<ModelForm>(() => {
    const base: ModelForm = {
      id: addMode ? '' : model,
      name: meta?.name ?? '',
      image: !!meta?.image_input,
      audio: !!meta?.audio_input,
      video: !!meta?.video_input,
      thinking: !!meta?.thinking,
      variants: (meta?.thinking_variants ?? []).join(', '),
      defaultVariant: meta?.thinking_default ?? '',
      contextWindow: meta?.context_window ? String(meta.context_window) : '',
      maxOutput: meta?.max_output_tokens ? String(meta.max_output_tokens) : '',
      outputModalities: (meta?.output_modalities ?? ['text']).join(', '),
      compat: meta?.compat,
      json: '',
    };
    return { ...base, json: buildJson(base) };
  });
  const [remoteList, setRemoteList] = useState<string[] | null>(null);
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [remoteError, setRemoteError] = useState<string | null>(null);
  const [newVariant, setNewVariant] = useState('');
  const [saving, setSaving] = useState(false);
  // The config file editor stays collapsed by default; the form projection is
  // enough for most edits and the JSON wins on save whenever it was touched.
  const [jsonOpen, setJsonOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const patch = (partial: Partial<ModelForm>) => {
    setForm((prev) => {
      const next = { ...prev, ...partial };
      return { ...next, json: buildJson(next) };
    });
  };

  /** Add one variant per click/Enter. A pasted multi-value string is split so
   *  the input itself always reads as a single level name. */
  const addVariant = () => {
    const parts = newVariant
      .split(/[,，;；\n]/)
      .map((x) => x.trim())
      .filter(Boolean);
    if (!parts.length) return;
    const list = splitList(form.variants);
    const next = [...list];
    for (const v of parts) {
      if (!next.includes(v)) next.push(v);
    }
    patch({ variants: next.join(', '), defaultVariant: form.defaultVariant || (next[0] ?? '') });
    setNewVariant('');
  };

  const removeVariant = (v: string) => {
    const list = splitList(form.variants).filter((x) => x !== v);
    patch({
      variants: list.join(', '),
      defaultVariant: form.defaultVariant === v ? (list[0] ?? '') : form.defaultVariant,
    });
  };

  const applyJson = () => {
    try {
      setForm((prev) => {
        const next = jsonToForm(prev.json, prev);
        next.json = buildJson(next);
        return next;
      });
      setError(null);
    } catch (err) {
      setError(
        `${t('llm.modelEdit.badJson')}: ${err instanceof Error ? err.message : String(err)}`
      );
    }
  };

  const fetchRemote = async () => {
    if (!providerId || remoteLoading) return;
    setRemoteLoading(true);
    setRemoteError(null);
    try {
      const list = await listRemoteModels(providerId);
      setRemoteList(list);
    } catch (err) {
      const e = err as { message?: string; hint?: string };
      setRemoteError(
        e.hint ? `${e.message}(${e.hint})` : (e.message ?? t('llm.provider.actionFailed'))
      );
    } finally {
      setRemoteLoading(false);
    }
  };

  const save = async () => {
    const id = form.id.trim();
    if (!id) {
      setError(t('llm.modelEdit.missingId'));
      return;
    }
    // The JSON text is authoritative: apply it automatically when it drifted
    // from the control projection, so a hand edit + Save works in one click.
    let f = form;
    if (form.json !== buildJson(form)) {
      try {
        f = jsonToForm(form.json, form);
      } catch (err) {
        setError(
          `${t('llm.modelEdit.badJson')}: ${err instanceof Error ? err.message : String(err)}`
        );
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(id, formToMeta(f));
    } catch (err) {
      setError(err instanceof Error ? err.message : t('llm.provider.actionFailed'));
    } finally {
      setSaving(false);
    }
  };

  const toggles: Array<{ label: string; on: boolean; set: (v: boolean) => void }> = [
    { label: t('llm.modelEdit.image'), on: form.image, set: (v) => patch({ image: v }) },
    { label: t('llm.modelEdit.audio'), on: form.audio, set: (v) => patch({ audio: v }) },
    { label: t('llm.modelEdit.video'), on: form.video, set: (v) => patch({ video: v }) },
  ];

  const title = addMode ? t('llm.modelEdit.addTitle') : t('llm.modelEdit.title', { model });

  return (
    <ModalOverlay open onClose={onClose}>
      <div
        className="modal glass-card--dialog llm-model-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="modal__title">{title}</h3>

        <div className="llm-model-dialog__grid">
          <div className="form-row">
            <label htmlFor="llm-model-id">{t('llm.modelEdit.modelId')}</label>
            <input
              id="llm-model-id"
              className="field input"
              value={form.id}
              readOnly={!addMode}
              onChange={(e) => patch({ id: e.target.value })}
              spellCheck={false}
            />
          </div>
          <div className="form-row">
            <label htmlFor="llm-model-name">{t('llm.modelEdit.name')}</label>
            <input
              id="llm-model-name"
              className="field input"
              value={form.name}
              onChange={(e) => patch({ name: e.target.value })}
              spellCheck={false}
            />
          </div>
        </div>

        {addMode && providerId ? (
          <div className="form-row">
            <label htmlFor="llm-model-remote">{t('llm.modelEdit.remoteListLabel')}</label>
            {remoteList === null ? (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={remoteLoading}
                onClick={() => void fetchRemote()}
              >
                {remoteLoading ? t('llm.modelEdit.fetchingList') : t('llm.modelEdit.fetchList')}
              </button>
            ) : remoteList.length ? (
              <GlassSelect
                id="llm-model-remote"
                value=""
                options={remoteList.map((m) => ({ value: m, label: m }))}
                onChange={(v) => v && patch({ id: v })}
                aria-label={t('llm.modelEdit.remoteListLabel')}
              />
            ) : (
              <p className="muted small">{t('llm.modelEdit.fetchListEmpty')}</p>
            )}
            {remoteError ? (
              <div className="setting-field__error small" role="alert">
                {remoteError}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="llm-model-dialog__grid">
          <div className="form-row">
            <label htmlFor="llm-model-window">{t('llm.modelEdit.contextWindow')}</label>
            <input
              id="llm-model-window"
              className="field input"
              inputMode="numeric"
              placeholder="200000"
              value={form.contextWindow}
              onChange={(e) => patch({ contextWindow: e.target.value })}
            />
          </div>
          <div className="form-row">
            <label htmlFor="llm-model-maxout">{t('llm.modelEdit.maxOutput')}</label>
            <input
              id="llm-model-maxout"
              className="field input"
              inputMode="numeric"
              placeholder="8192"
              value={form.maxOutput}
              onChange={(e) => patch({ maxOutput: e.target.value })}
            />
          </div>
        </div>

        <div className="form-row">
          <label>{t('llm.modelEdit.inputTypes')}</label>
          <div
            className="llm-model-dialog__toggles"
            role="group"
            aria-label={t('llm.modelEdit.inputTypes')}
          >
            {toggles.map((tg) => (
              <button
                key={tg.label}
                type="button"
                className={`llm-model-toggle ${tg.on ? 'is-on' : ''}`}
                aria-pressed={tg.on}
                onClick={() => tg.set(!tg.on)}
              >
                {tg.label}
              </button>
            ))}
          </div>
        </div>

        <div className="form-row">
          <label>{t('llm.modelEdit.reasoning')}</label>
          <div className="llm-model-dialog__toggles">
            <button
              type="button"
              className={`llm-model-toggle ${form.thinking ? 'is-on' : ''}`}
              aria-pressed={form.thinking}
              onClick={() => patch({ thinking: !form.thinking })}
            >
              {t('llm.modelEdit.supportsThinking')}
            </button>
          </div>
        </div>

        {form.thinking ? (
          <>
            <div className="form-row">
              <label htmlFor="llm-model-variant-input">{t('llm.modelEdit.thinkingVariants')}</label>
              <div className="llm-key-field">
                <input
                  id="llm-model-variant-input"
                  className="field input"
                  value={newVariant}
                  placeholder={t('llm.modelEdit.variantsPlaceholder')}
                  onChange={(e) => setNewVariant(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      addVariant();
                    }
                  }}
                  spellCheck={false}
                />
                <button type="button" className="btn btn-ghost btn-sm" onClick={addVariant}>
                  +
                </button>
              </div>
              {splitList(form.variants).length ? (
                <div className="llm-variant-list">
                  {splitList(form.variants).map((v) => {
                    const isDefault = form.defaultVariant === v;
                    return (
                      <span
                        key={v}
                        className={`llm-variant-chip ${isDefault ? 'is-default' : ''}`}
                        role="button"
                        tabIndex={0}
                        title={t('llm.modelEdit.setDefaultVariant')}
                        onClick={() => patch({ defaultVariant: v })}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') patch({ defaultVariant: v });
                        }}
                      >
                        {v}
                        {isDefault ? (
                          <span className="llm-variant-chip__default">
                            {t('llm.modelEdit.defaultBadge')}
                          </span>
                        ) : null}
                        <button
                          type="button"
                          className="llm-variant-chip__remove"
                          aria-label={t('llm.modelEdit.removeVariant', { variant: v })}
                          onClick={(e) => {
                            e.stopPropagation();
                            removeVariant(v);
                          }}
                        >
                          ×
                        </button>
                      </span>
                    );
                  })}
                </div>
              ) : null}
            </div>
          </>
        ) : null}

        <div className="llm-config-head">
          <label htmlFor="llm-model-json">{t('llm.modelEdit.configFile')}</label>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setJsonOpen(!jsonOpen)}
          >
            {jsonOpen ? t('llm.provider.applyConfigCancel') : t('llm.provider.editConfig')}
          </button>
        </div>
        {jsonOpen ? (
          <>
            <textarea
              id="llm-model-json"
              className="llm-json-editor"
              value={form.json}
              onChange={(e) => setForm((prev) => ({ ...prev, json: e.target.value }))}
              rows={12}
              spellCheck={false}
            />
            <div className="llm-config-actions">
              <button type="button" className="btn btn-ghost btn-sm" onClick={applyJson}>
                {t('llm.modelEdit.applyJson')}
              </button>
            </div>
          </>
        ) : null}

        {error ? (
          <div className="setting-field__error small" role="alert">
            {error}
          </div>
        ) : null}

        <div className="modal__actions">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t('llm.modelEdit.cancel')}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={saving}
            onClick={() => void save()}
          >
            {addMode ? t('llm.provider.addModel') : t('llm.modelEdit.save')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
