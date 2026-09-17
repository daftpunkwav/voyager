/**
 * @file LlmModelEditDialog
 * @description Per-model configuration dialog (llm settings): capability flags
 * (image/audio/video input, thinking) plus the token budgets (context window,
 * max output tokens). Pure form state; saving hands the assembled LlmModelMeta
 * to the caller, which patches models_meta and mirrors the budgets into
 * agent.context.model_profiles. Shell is the shared ModalOverlay (portal +
 * scrim + enter/exit animation).
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { LlmModelMeta } from '@/api/types';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface LlmModelEditDialogProps {
  model: string;
  meta: LlmModelMeta;
  onSave: (meta: LlmModelMeta) => Promise<void>;
  onClose: () => void;
}

export function LlmModelEditDialog({ model, meta, onSave, onClose }: LlmModelEditDialogProps) {
  const { t } = useTranslation('settings');
  const [contextWindow, setContextWindow] = useState(
    meta.context_window ? String(meta.context_window) : ''
  );
  const [maxOutput, setMaxOutput] = useState(
    meta.max_output_tokens ? String(meta.max_output_tokens) : ''
  );
  const [image, setImage] = useState(!!meta.image_input);
  const [audio, setAudio] = useState(!!meta.audio_input);
  const [video, setVideo] = useState(!!meta.video_input);
  const [thinking, setThinking] = useState(!!meta.thinking);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** undefined = leave unset; null = invalid input (blocks saving). */
  const parseBudget = (raw: string): number | null | undefined => {
    const trimmed = raw.trim();
    if (!trimmed) return undefined;
    const n = Number(trimmed);
    return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
  };

  const save = async () => {
    const win = parseBudget(contextWindow);
    const out = parseBudget(maxOutput);
    if (win === null || out === null) {
      setError(t('llm.modelEdit.invalidNumber'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({
        image_input: image,
        audio_input: audio,
        video_input: video,
        thinking,
        ...(win === undefined ? {} : { context_window: win }),
        ...(out === undefined ? {} : { max_output_tokens: out }),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('llm.provider.actionFailed'));
    } finally {
      setSaving(false);
    }
  };

  const toggles: Array<{ label: string; on: boolean; set: (v: boolean) => void }> = [
    { label: t('llm.modelEdit.image'), on: image, set: setImage },
    { label: t('llm.modelEdit.audio'), on: audio, set: setAudio },
    { label: t('llm.modelEdit.video'), on: video, set: setVideo },
  ];

  return (
    <ModalOverlay open onClose={onClose}>
      <div
        className="modal glass-card--dialog llm-model-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t('llm.modelEdit.title', { model })}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="modal__title">{t('llm.modelEdit.title', { model })}</h3>

        <div className="form-row">
          <label htmlFor="llm-model-id">{t('llm.modelEdit.modelId')}</label>
          <input id="llm-model-id" className="field input" value={model} readOnly />
        </div>

        <div className="llm-model-dialog__grid">
          <div className="form-row">
            <label htmlFor="llm-model-window">{t('llm.modelEdit.contextWindow')}</label>
            <input
              id="llm-model-window"
              className="field input"
              inputMode="numeric"
              placeholder="200000"
              value={contextWindow}
              onChange={(e) => setContextWindow(e.target.value)}
            />
          </div>
          <div className="form-row">
            <label htmlFor="llm-model-maxout">{t('llm.modelEdit.maxOutput')}</label>
            <input
              id="llm-model-maxout"
              className="field input"
              inputMode="numeric"
              placeholder="8192"
              value={maxOutput}
              onChange={(e) => setMaxOutput(e.target.value)}
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
                <span className="llm-model-toggle__check" aria-hidden>
                  ✓
                </span>
                {tg.label}
              </button>
            ))}
          </div>
        </div>

        <div className="form-row">
          <label>{t('llm.modelEdit.capabilities')}</label>
          <div
            className="llm-model-dialog__toggles"
            role="group"
            aria-label={t('llm.modelEdit.capabilities')}
          >
            <button
              type="button"
              className={`llm-model-toggle ${thinking ? 'is-on' : ''}`}
              aria-pressed={thinking}
              onClick={() => setThinking(!thinking)}
            >
              <span className="llm-model-toggle__check" aria-hidden>
                ✓
              </span>
              {t('llm.modelEdit.thinking')}
            </button>
          </div>
        </div>

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
            {t('llm.modelEdit.save')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
