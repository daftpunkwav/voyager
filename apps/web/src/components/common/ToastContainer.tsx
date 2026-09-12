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

/** A single toast: plays the exit animation (toast-out) when its time is up, and is removed only after the animation ends */
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
        onClick={() => onRemove(toast.id)}
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
