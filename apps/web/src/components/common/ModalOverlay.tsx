/**
 * @file ModalOverlay
 * @description Shared modal shell: portal to document.body, dimmed scrim,
 * Escape/overlay-click to close, and symmetric enter/exit animations (exit is
 * faster than enter, per the motion craft bar). Must stay mounted while `open`
 * toggles, so it owns the leaving state internally.
 *
 * Responsibilities:
 * - Keep children mounted through the exit animation, then stop rendering
 * - Overlay click and Escape route to onClose; modals mark themselves with
 *   role="dialog" and stop propagation on their own surface
 */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface ModalOverlayProps {
  open: boolean;
  onClose: () => void;
  /** Extra classes for the overlay root (e.g. layout-specific modifiers) */
  className?: string;
  /** aria-labelledby id rendered by the dialog inside */
  children: React.ReactNode;
}

/** Keep this in sync with the --modal-out duration in global.css */
export const MODAL_EXIT_MS = 160;

export function ModalOverlay({ open, onClose, className, children }: ModalOverlayProps) {
  // `seenOpen` keeps the first enter from being treated as an exit; `leaving`
  // holds the overlay mounted for the exit animation before it unmounts.
  const seenOpen = useRef(open);
  const [leaving, setLeaving] = useState(false);

  if (open) seenOpen.current = true;

  useEffect(() => {
    if (!open && seenOpen.current) {
      seenOpen.current = false;
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), MODAL_EXIT_MS);
      return () => window.clearTimeout(timer);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open && !leaving) return null;

  return createPortal(
    <div
      className={`modal-overlay${leaving ? ' is-leaving' : ''}${className ? ` ${className}` : ''}`}
      role="presentation"
      onClick={onClose}
    >
      {children}
    </div>,
    document.body
  );
}
