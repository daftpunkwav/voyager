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

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useUIStore } from '@/stores/uiStore';

interface LightboxProps {
  src: string | null;
  alt?: string;
  onClose: () => void;
}

/** Keep in sync with the --modal-out duration in global.css */
const LIGHTBOX_EXIT_MS = 160;

export function Lightbox({ src, alt, onClose }: LightboxProps) {
  const { t } = useTranslation('common');
  // `seenSrc` + `leaving` keep the lightbox mounted through its exit animation
  // after the parent clears src (same lifecycle as ModalOverlay). seenSrc
  // deliberately keeps the last src while closed: the leaving render below
  // draws from it, and the next open overwrites it.
  const seenSrc = useRef<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  if (src) seenSrc.current = src;
  const visible = Boolean(src) || leaving;

  useEffect(() => {
    if (src) {
      // Re-open (or switch image) during the exit window: the deps change
      // already cleared the pending timer via cleanup, but `leaving` would
      // stay true and pin the lightbox on is-leaving forever.
      setLeaving(false);
      return;
    }
    if (seenSrc.current) {
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), LIGHTBOX_EXIT_MS);
      return () => window.clearTimeout(timer);
    }
  }, [src]);

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
