/**
 * @file ToastContainer
 * @description Bottom toast stack driven by uiStore; renders semantic-colored capsules with an aria-live region.
 *
 * Responsibilities:
 * - Subscribe to uiStore toasts and render bottom-centered semantic capsules
 * - Play the exit animation first and remove a toast only after it ends
 * - Keep an aria-live region and describe error payloads via error codes
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Toast } from '@/stores/uiStore';
import { useUIStore } from '@/stores/uiStore';
import { describeError } from '@/utils/errorCodes';

/** Decorative type glyph so the severity reads at a glance; color comes from
 *  the semantic toast variant. */
function ToastIcon({ type }: { type: Toast['type'] }) {
  const common = {
    width: 16,
    height: 16,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2.2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
  switch (type) {
    case 'success':
      return (
        <svg {...common} className="toast__icon">
          <path d="M20 6 9 17l-5-5" />
        </svg>
      );
    case 'error':
      return (
        <svg {...common} className="toast__icon">
          <circle cx="12" cy="12" r="9.5" />
          <path d="m15 9-6 6M9 9l6 6" />
        </svg>
      );
    case 'warning':
      return (
        <svg {...common} className="toast__icon">
          <path d="M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
      );
    default:
      return (
        <svg {...common} className="toast__icon">
          <circle cx="12" cy="12" r="9.5" />
          <path d="M12 16v-5M12 8h.01" />
        </svg>
      );
  }
}

/** A single toast: plays the exit animation (toast-out) when its time is up or
 * when dismissed manually, and is removed only after the animation ends */
function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: (id: string) => void }) {
  // Subscribes to languageChanged so an in-flight toast re-renders its
  // errors-namespace title/hint when the UI language switches.
  const { t } = useTranslation(['errors', 'common']);
  const [leaving, setLeaving] = useState(false);
  const duration = toast.duration ?? 3000;

  useEffect(() => {
    const t = setTimeout(() => setLeaving(true), duration);
    return () => clearTimeout(t);
  }, [duration]);

  const desc = toast.code ? describeError(toast.code) : null;
  const title = desc?.title ?? toast.message;

  return (
    <div
      className={`toast toast--${toast.type}${leaving ? ' toast--leaving' : ''}`}
      role="alert"
      onAnimationEnd={() => {
        if (leaving) onRemove(toast.id);
      }}
    >
      <ToastIcon type={toast.type} />
      <div className="toast__body">
        <div className="toast__row">
          {toast.code && (
            <span className="toast-code" data-testid="toast-code">
              [{toast.code}]
            </span>
          )}
          <span className="toast-title">{title}</span>
        </div>
        {desc?.hint && <span className="toast-hint">{desc.hint}</span>}
      </div>
      <button
        type="button"
        className="toast__close"
        onClick={() => setLeaving(true)}
        aria-label={t('common:action.close')}
      >
        ×
      </button>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useUIStore((s) => s.toasts);
  const removeToast = useUIStore((s) => s.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div className="toast-container" aria-live="polite" role="alert">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onRemove={removeToast} />
      ))}
    </div>
  );
}
