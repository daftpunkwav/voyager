/**
 * @file AskDialog
 * @description Modal for agent.ask questions. The model picks the answer form
 * freely: confirm (yes/no), choice (single pick, 2-8 options), multi_choice
 * (any subset, submit an array), slider (numeric or a labeled discrete scale
 * with 1-8 tick labels), rating (five stars, answered as 1-5), text (free
 * input) — and every dialog carries a permanent free-text input, so options
 * are suggestions rather than a fence: the user may always type their own
 * answer regardless of kind. Unknown kinds degrade to the free-text form.
 *
 * Shared by the chat page and the persistent floating window; lives in the
 * widgets layer so page-private components are never depended on in reverse.
 *
 * Responsibilities:
 * - Render the per-kind widgets (buttons / toggles / slider / stars)
 * - Keep a free-text input permanently available on every dialog
 * - Post answers back via answer_question and surface service errors
 * - Close on the frontend fallback timeout when no backend reply arrives
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import { answerQuestion } from '@/api/agent';
import { useChatStore } from '@/stores/chatStore';

/** Frontend fallback timeout: the backend Question expires after 120s by default
 * (see agent/tools/interact/ask_user.py) and its Future is discarded; the frontend waits
 * 10s longer before closing the dialog so the UI never sticks on a question that
 * can no longer be matched. */
const ANSWER_WINDOW_MS = 130_000;

export function AskDialog() {
  const { t } = useTranslation('chat');
  const question = useChatStore((s) => s.question);
  const clearQuestion = useChatStore((s) => s.clearQuestion);
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [customOptions, setCustomOptions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const questionId = question?.questionId;
  // A new question must never inherit the previous draft/selection
  useEffect(() => {
    setText('');
    setSelected([]);
    setCustomOptions([]);
    setError(null);
  }, [questionId]);

  // Timeout fallback: the answer_question Future only lives while the ask is
  // pending; a late answer is guaranteed to miss
  useEffect(() => {
    if (!questionId) return;
    const timer = setTimeout(() => {
      useChatStore.getState().addSystem(t('chat:ask.timeout'));
      useChatStore.getState().clearQuestion();
    }, ANSWER_WINDOW_MS);
    return () => clearTimeout(timer);
  }, [questionId, t]);

  if (!question) return null;

  const isMulti = question.kind === 'multi_choice';
  const presetOptions = question.options;
  const allOptions = [...presetOptions, ...customOptions.filter((c) => !presetOptions.includes(c))];

  const submit = async (raw: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const out = await answerQuestion({
        question_id: question.questionId,
        value: raw,
      });
      if (out.matched === false) {
        // The question no longer exists backend-side (expired and discarded): inform
        // the user and close normally so the conversation can continue
        useChatStore.getState().addSystem(t('chat:ask.expired'));
      }
      clearQuestion();
      setText('');
      setSelected([]);
      setCustomOptions([]);
    } catch (err) {
      setError((err as ServiceError).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleMulti = (opt: string) => {
    setSelected((prev) => (prev.includes(opt) ? prev.filter((v) => v !== opt) : [...prev, opt]));
  };

  const addCustomOption = () => {
    const value = text.trim();
    if (!value || allOptions.includes(value)) return;
    setCustomOptions((prev) => [...prev, value]);
    setSelected((prev) => [...prev, value]);
    setText('');
  };

  const sliderNumber = Number(text);
  const textIsNumber = text.trim() !== '' && Number.isFinite(sliderNumber);
  const numericAnswerKind = question.kind === 'slider' || question.kind === 'rating';

  return (
    <div className="ask-mask" role="dialog" aria-modal="true" aria-label={question.prompt}>
      <div className="ask-dialog glass-card glass-card--dialog">
        <div className="ask-dialog__prompt">{question.prompt}</div>

        {question.kind === 'choice' && allOptions.length > 0 ? (
          <div className="ask-options">
            {allOptions.map((opt, i) => (
              <button
                type="button"
                key={`${opt}-${i}`}
                className="ask-option"
                disabled={busy}
                onClick={() => void submit(opt)}
              >
                {opt}
              </button>
            ))}
          </div>
        ) : null}

        {isMulti && allOptions.length > 0 ? (
          <div className="ask-options">
            {allOptions.map((opt, i) => (
              <button
                type="button"
                key={`${opt}-${i}`}
                className={`ask-option${selected.includes(opt) ? ' ask-option--selected' : ''}`}
                aria-pressed={selected.includes(opt)}
                disabled={busy}
                onClick={() => toggleMulti(opt)}
              >
                {selected.includes(opt) ? '☑ ' : '☐ '}
                {opt}
              </button>
            ))}
          </div>
        ) : null}

        {isMulti ? (
          <div className="ask-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || selected.length === 0}
              onClick={() => void submit(selected)}
            >
              {t('chat:ask.multiSubmit')}
            </button>
          </div>
        ) : null}

        {question.kind === 'slider' ? (
          allOptions.length > 0 ? (
            <LabeledSliderAsk labels={allOptions} busy={busy} onSubmit={submit} />
          ) : (
            <SliderAsk min={question.min} max={question.max} busy={busy} onSubmit={submit} />
          )
        ) : null}

        {question.kind === 'rating' ? <StarsAsk busy={busy} onSubmit={submit} /> : null}

        {question.kind === 'confirm' ? (
          <div className="ask-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() => void submit(true)}
            >
              {t('chat:ask.confirm')}
            </button>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={() => void submit(false)}
            >
              {t('chat:ask.cancel')}
            </button>
          </div>
        ) : null}

        {/* Permanent free-text input: options are suggestions, never a fence.
            For text/unknown kinds this is the primary answer; for the rest it
            is the always-available custom answer. */}
        <div className="ask-custom">
          <input
            className="setting-input"
            value={text}
            autoFocus={question.kind === 'text' || allOptions.length === 0}
            placeholder={t('chat:ask.customPlaceholder')}
            disabled={busy}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                if (isMulti) {
                  addCustomOption();
                  return;
                }
                if (text.trim()) {
                  void submit(numericAnswerKind && textIsNumber ? sliderNumber : text.trim());
                }
              }
            }}
          />
          {isMulti ? (
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy || !text.trim()}
              onClick={addCustomOption}
            >
              {t('chat:ask.addOption')}
            </button>
          ) : null}
          {question.kind !== 'text' && !isMulti ? (
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy || !text.trim()}
              onClick={() =>
                void submit(numericAnswerKind && textIsNumber ? sliderNumber : text.trim())
              }
            >
              {t('chat:ask.customAnswer')}
            </button>
          ) : null}
        </div>

        {question.kind === 'text' ? (
          <div className="ask-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !text.trim()}
              onClick={() => void submit(text.trim())}
            >
              {t('chat:ask.answer')}
            </button>
          </div>
        ) : null}

        {error ? <div className="setting-field__error small">{error}</div> : null}
      </div>
    </div>
  );
}

function SliderAsk({
  min,
  max,
  busy,
  onSubmit,
}: {
  min: number | null;
  max: number | null;
  busy: boolean;
  onSubmit: (v: number) => Promise<void>;
}) {
  const { t } = useTranslation('chat');
  const lo = min ?? 0;
  const hi = max ?? 100;
  const [v, setV] = useState(Math.round((lo + hi) / 2));
  return (
    <>
      <div className="small muted mono ask-slider-value">{v}</div>
      <input
        type="range"
        className="ask-slider"
        min={lo}
        max={hi}
        value={v}
        disabled={busy}
        onChange={(e) => setV(Number(e.target.value))}
      />
      <div className="ask-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void onSubmit(v)}
        >
          {t('chat:ask.answer')}
        </button>
      </div>
    </>
  );
}

/** Discrete scale over 1-8 tick labels: the answer is the picked label text. */
function LabeledSliderAsk({
  labels,
  busy,
  onSubmit,
}: {
  labels: string[];
  busy: boolean;
  onSubmit: (v: string) => Promise<void>;
}) {
  const { t } = useTranslation('chat');
  const [idx, setIdx] = useState(0);
  return (
    <>
      <input
        type="range"
        className="ask-slider"
        min={1}
        max={labels.length}
        value={idx + 1}
        disabled={busy}
        onChange={(e) => setIdx(Number(e.target.value) - 1)}
      />
      <div className="ask-scale" role="status">
        {labels.map((label, i) => (
          <span key={label} className={`small${i === idx ? ' ask-scale__label--on' : ' muted'}`}>
            {label}
          </span>
        ))}
      </div>
      <div className="ask-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void onSubmit(labels[idx])}
        >
          {t('chat:ask.answer')}
        </button>
      </div>
    </>
  );
}

/** Five-star review: click a star to set, then submit — the answer is 1-5. */
function StarsAsk({ busy, onSubmit }: { busy: boolean; onSubmit: (v: number) => Promise<void> }) {
  const { t } = useTranslation('chat');
  const [stars, setStars] = useState(0);
  return (
    <>
      <div className="ask-stars" role="radiogroup" aria-label={t('chat:ask.starsAria')}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            className={`ask-star${n <= stars ? ' ask-star--on' : ''}`}
            aria-pressed={stars >= n}
            aria-label={t('chat:ask.starN', { n })}
            disabled={busy}
            onClick={() => setStars(n)}
          >
            ★
          </button>
        ))}
      </div>
      <div className="ask-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || stars === 0}
          onClick={() => void onSubmit(stars)}
        >
          {t('chat:ask.answer')}
        </button>
      </div>
    </>
  );
}
