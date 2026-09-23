/**
 * @file Lightbox
 * @description Image lightbox: click to zoom, close via Escape or the overlay.
 *
 * Follows the global motion conventions (automatic reduced-motion fallback).
 * While open it increments uiStore.modalDepth so page-level Escape shortcuts
 * (e.g. notes back to list) yield to the lightbox first.
 *
 * Responsibilities:
 * - Render the zoomed image over an overlay; close via overlay click or Escape
 * - Raise uiStore.modalDepth while open so page-level Escape yields to it first
 */

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '@/stores/uiStore';
import { useLeaving } from '@/hooks/useLeaving';

interface LightboxProps {
  src: string | null;
  alt?: string;
  onClose: () => void;
}

/** Keep in sync with the --modal-out duration in global.css */
const LIGHTBOX_EXIT_MS = 160;

export function Lightbox({ src, alt, onClose }: LightboxProps) {
  const { t } = useTranslation('common');
  // `seenSrc` keeps the last src while closed: the leaving render below draws
  // from it, and the next open overwrites it. The mount-through-exit lifecycle
  // (leaving flag + reopen recovery) is the shared useLeaving hook.
  const seenSrc = useRef<string | null>(null);
  if (src) seenSrc.current = src;
  const leaving = useLeaving(Boolean(src), LIGHTBOX_EXIT_MS);
  const visible = Boolean(src) || leaving;

  useEffect(() => {
    if (!src) return;
    useUIStore.getState().pushModal();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      useUIStore.getState().popModal();
      window.removeEventListener('keydown', onKey);
    };
  }, [src, onClose]);

  if (!visible) return null;
  return (
    <div
      className={`lightbox${!src && leaving ? ' is-leaving' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label={alt ?? t('common:lightbox.preview')}
      onClick={onClose}
    >
      <img src={seenSrc.current ?? src ?? ''} alt={alt ?? ''} className="lightbox__img" />
      <button
        type="button"
        className="lightbox__close"
        aria-label={t('common:action.close')}
        onClick={onClose}
      >
        ✕
      </button>
    </div>
  );
}
