/**
 * @file ChatComposer
 * @description Shared chat composer: textarea plus a bottom bar holding the
 * workspace path (far left), then — right-aligned after a spacer — the
 * context-usage ring, the model picker, the reasoning-effort picker and the
 * send/stop control (mainstream-agent layout). Used by the
 * chat page and the persistent floating window; each surface owns its own
 * useChatSend instance.
 *
 * Responsibilities:
 * - Bind the draft and disable on sending / llmMissing / empty draft
 * - Enter sends, Shift+Enter inserts a newline, IME composition never sends
 * - While the agent is running the button morphs into stop (interrupt)
 * - Model picker writes llm.default_provider + llm.default_model so the next
 *   turn routes to the selection; grouped by provider with a settings entry
 * - Reasoning picker: the level list comes from the selected model's
 *   configured thinking_variants (settings page = single source of truth),
 *   displayed verbatim (low / high / max...); "off" is the explicit disable.
 *   The choice writes llm.reasoning_effort (off / variant name); an empty
 *   setting follows the model's thinking_default. Disabled unless the
 *   selected model declares thinking support in its models_meta
 * - ContextRing shows the active session's window usage (own polling)
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmModelMeta, LlmProvider } from '@/api/types';
import { listProviders, firstEnabledModel } from '@/api/llm';
import { LLM_MODEL_KEY, LLM_PROVIDER_KEY, LLM_REASONING_EFFORT_KEY } from '@/api/settings';
import type { UseChatSendReturn } from '@/hooks/useChatSend';
import { Popover } from '@/components/common/Popover';
import { ContextRing } from '@/widgets/chat/ContextRing';
import { WorkspacePathChip } from '@/widgets/chat/WorkspaceChip';

interface ChatComposerProps {
  /** Send state from the surface-owned useChatSend instance */
  composer: UseChatSendReturn;
  /** Placeholder copy; callers with an llmMissing degrade tip pass the swapped copy here */
  placeholder: string;
  /** Wrapper class: the page and the floating panel lay the composer out differently */
  className: string;
  /** The agent is running: the send button becomes the stop button */
  running?: boolean;
  /** Interrupt the current turn (required when running is passed) */
  onStop?: () => void;
  /** Test seam: providers injected instead of fetched from the llm service */
  providers?: LlmProvider[];
  /** "Manage models" entry; omitted (e.g. in tests) hides the entry */
  onManageModels?: () => void;
}

/** One dropdown in the composer bar: trigger button + popup list. Open/close
 *  behavior and the anchored enter/exit motion live in the shared Popover. */
function BarDropdown({
  label,
  ariaLabel,
  disabled,
  children,
}: {
  label: React.ReactNode;
  ariaLabel: string;
  disabled?: boolean;
  children: (close: () => void) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  return (
    <div className="composer-dd" ref={ref}>
      <button
        type="button"
        className="composer-dd__trigger"
        aria-label={ariaLabel}
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(!open)}
      >
        {label}
        <svg
          width={10}
          height={10}
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={ref}
        direction="up"
        role="listbox"
        className="composer-dd__pop glass-card glass-card--dialog"
      >
        {() => children(() => setOpen(false))}
      </Popover>
    </div>
  );
}

/** Explicit-disable sentinel stored in llm.reasoning_effort ("" means the
 *  opposite: follow the model's configured thinking_default). */
const EFFORT_OFF = 'off';

/** Variants for models that declare thinking support without a configured
 *  variant list (legacy configs): the pre-variants canonical set. */
const FALLBACK_VARIANTS = ['low', 'medium', 'high'];

/** Mirror of the backend resolution (llm resolve_reasoning_effort): what the
 *  stored override actually means for this model. The displayed level and
 *  the wire value must agree, so both sides resolve the same way — "" follows
 *  the model's thinking_default, "off" disables, anything else must be one
 *  of the model's thinking_variants (stale values from a previous model fall
 *  back to the default); models without variants keep the canonical set. */
function resolveEffort(setting: string, meta: LlmModelMeta | undefined): string {
  if (setting === EFFORT_OFF) return '';
  const variants = meta?.thinking_variants ?? [];
  const fallback = meta?.thinking_default ?? '';
  if (setting) {
    if (variants.length) return variants.includes(setting) ? setting : fallback;
    return FALLBACK_VARIANTS.includes(setting) ? setting : '';
  }
  return variants.length || meta?.thinking === true ? fallback : '';
}

function SparklesIcon() {
  return (
    <svg
      width={13}
      height={13}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" />
      <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15z" />
    </svg>
  );
}

export function ChatComposer({
  composer,
  placeholder,
  className,
  running = false,
  onStop,
  providers: providersProp,
  onManageModels,
}: ChatComposerProps) {
  const { t } = useTranslation('chat');
  const { draft, setDraft, sending, llmMissing, send } = composer;
  const stopping = running && Boolean(onStop);

  const [providers, setProviders] = useState<LlmProvider[]>(providersProp ?? []);
  const [providerId, setProviderId] = useState('');
  const [model, setModel] = useState('');
  const [reasoning, setReasoning] = useState('');

  // Load the catalog + the persisted selection once; test injections skip the fetch.
  useEffect(() => {
    if (providersProp) {
      setProviders(providersProp);
      return;
    }
    let alive = true;
    listProviders()
      .then((ps) => {
        if (alive) setProviders(ps.filter((p) => p.enabled && p.has_api_key));
      })
      .catch(() => {}); // picker degrades to disabled; composing still works
    const keys: Array<[string, (v: string) => void]> = [
      [LLM_PROVIDER_KEY, setProviderId],
      [LLM_MODEL_KEY, setModel],
      [LLM_REASONING_EFFORT_KEY, setReasoning],
    ];
    for (const [key, apply] of keys) {
      callCapability<{ value?: unknown }>('settings', 'get_setting', { key })
        .then((item) => {
          if (alive && item && typeof item.value === 'string') apply(item.value);
        })
        .catch(() => {});
    }
    return () => {
      alive = false;
    };
  }, [providersProp]);

  const currentProvider = providers.find((p) => p.id === providerId) ?? null;
  const selectedModel = model || firstEnabledModel(currentProvider);
  const meta = currentProvider?.models_meta?.[selectedModel];
  const thinkingSupported = meta ? meta.thinking === true : false;
  // The menu lists the model's configured variants verbatim (settings page =
  // single source); the checkmark and the trigger label show the RESOLVED
  // level, so what the user sees always matches what the backend will send.
  const variants = thinkingSupported
    ? meta?.thinking_variants?.length
      ? meta.thinking_variants
      : FALLBACK_VARIANTS
    : [];
  const effectiveEffort = resolveEffort(reasoning, meta);

  const pickModel = (p: LlmProvider, m: string) => {
    setProviderId(p.id);
    setModel(m);
    void callCapability('settings', 'set_setting', { key: LLM_PROVIDER_KEY, value: p.id })
      .catch(() => {})
      .then(() => callCapability('settings', 'set_setting', { key: LLM_MODEL_KEY, value: m }))
      .catch(() => {});
  };

  const pickReasoning = (value: string) => {
    setReasoning(value);
    void callCapability('settings', 'set_setting', {
      key: LLM_REASONING_EFFORT_KEY,
      value,
    }).catch(() => {});
  };

  return (
    <div className={className}>
      <textarea
        rows={2}
        value={draft}
        placeholder={placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          // isComposing: Enter that confirms an IME candidate must not send
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void send();
          }
        }}
      />
      <div className="composer-bar">
        <WorkspacePathChip />
        <span className="composer-bar__spacer" />
        <ContextRing />
        <BarDropdown
          label={
            <>
              <span className="composer-dd__text">
                {selectedModel || t('chat:composer.modelNone')}
              </span>
            </>
          }
          ariaLabel={t('chat:composer.modelAria')}
          disabled={providers.length === 0}
        >
          {(close) => (
            <>
              {providers.map((p) => (
                <div key={p.id} className="composer-dd__group">
                  <div className="composer-dd__group-title">{p.display_name || p.id}</div>
                  {p.models.map((m) => (
                    <button
                      key={m}
                      type="button"
                      role="option"
                      aria-selected={p.id === providerId && m === selectedModel}
                      className="composer-dd__item"
                      onClick={() => {
                        pickModel(p, m);
                        close();
                      }}
                    >
                      {m}
                      {p.models_meta?.[m]?.image_input ? (
                        <span className="composer-dd__badge">{t('chat:composer.badgeImage')}</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              ))}
              {onManageModels ? (
                <button
                  type="button"
                  className="composer-dd__item composer-dd__item--manage"
                  onClick={() => {
                    close();
                    onManageModels();
                  }}
                >
                  {t('chat:composer.manageModels')}
                </button>
              ) : null}
            </>
          )}
        </BarDropdown>
        <BarDropdown
          label={
            <>
              <SparklesIcon />
              <span className="composer-dd__text">{effectiveEffort || t('chat:thinking.off')}</span>
            </>
          }
          ariaLabel={t('chat:thinking.aria')}
          disabled={!thinkingSupported}
        >
          {(close) => (
            <>
              <button
                type="button"
                role="option"
                aria-selected={effectiveEffort === ''}
                className="composer-dd__item"
                onClick={() => {
                  pickReasoning(EFFORT_OFF);
                  close();
                }}
              >
                {t('chat:thinking.off')}
                {effectiveEffort === '' ? <span aria-hidden>✓</span> : null}
              </button>
              {variants.map((variant) => (
                <button
                  key={variant}
                  type="button"
                  role="option"
                  aria-selected={variant === effectiveEffort}
                  className="composer-dd__item"
                  onClick={() => {
                    pickReasoning(variant);
                    close();
                  }}
                >
                  {variant}
                  {variant === effectiveEffort ? <span aria-hidden>✓</span> : null}
                </button>
              ))}
            </>
          )}
        </BarDropdown>
        {stopping ? (
          <button type="button" className="btn btn-danger chat-stop" onClick={onStop}>
            {t('chat:composer.stop')}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary chat-send"
            disabled={sending || llmMissing || !draft.trim()}
            onClick={() => void send()}
            aria-label={t('chat:composer.send')}
          >
            <svg
              width={16}
              height={16}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden
            >
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
