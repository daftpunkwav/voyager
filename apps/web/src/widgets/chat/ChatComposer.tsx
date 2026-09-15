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
 * - Reasoning picker writes llm.reasoning_effort (off/low/medium/high); the
 *   backend injects it into supported wire formats. Disabled unless the
 *   selected model declares thinking support in its models_meta
 * - ContextRing shows the active session's window usage (own polling)
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import type { LlmProvider } from '@/api/types';
import { listProviders } from '@/api/llm';
import { LLM_MODEL_KEY, LLM_PROVIDER_KEY, LLM_REASONING_EFFORT_KEY } from '@/api/settings';
import type { UseChatSendReturn } from '@/hooks/useChatSend';
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

/** One dropdown in the composer bar: trigger button + popup list, closes on
 *  outside click / Escape. */
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

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

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
      {open ? (
        <div className="composer-dd__pop glass-card glass-card--dialog" role="listbox">
          {children(() => setOpen(false))}
        </div>
      ) : null}
    </div>
  );
}

/** Reasoning levels (stored value -> label key); "" means do not send. */
const THINKING_LEVELS: Array<{ value: string; labelKey: string }> = [
  { value: '', labelKey: 'chat:thinking.off' },
  { value: 'low', labelKey: 'chat:thinking.low' },
  { value: 'medium', labelKey: 'chat:thinking.medium' },
  { value: 'high', labelKey: 'chat:thinking.high' },
];

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
  const selectedModel = model || currentProvider?.default_model || '';
  const meta = currentProvider?.models_meta?.[selectedModel];
  const thinkingSupported = meta ? meta.thinking === true : false;

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

  const reasoningLabel =
    THINKING_LEVELS.find((l) => l.value === reasoning)?.labelKey ?? 'chat:thinking.off';

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
              <span className="composer-dd__text">{t(reasoningLabel)}</span>
            </>
          }
          ariaLabel={t('chat:thinking.aria')}
          disabled={!thinkingSupported}
        >
          {(close) => (
            <>
              {THINKING_LEVELS.map((level) => (
                <button
                  key={level.value}
                  type="button"
                  role="option"
                  aria-selected={level.value === reasoning}
                  className="composer-dd__item"
                  onClick={() => {
                    pickReasoning(level.value);
                    close();
                  }}
                >
                  {t(level.labelKey)}
                  {level.value === reasoning ? <span aria-hidden>✓</span> : null}
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
