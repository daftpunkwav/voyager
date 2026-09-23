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
 * - Track a module-level open stack so Escape only closes the topmost modal
 *   (a confirm dialog layered over a browser modal closes alone), and raise
 *   uiStore.modalDepth while open so page-level Esc handling yields
 */
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useUIStore } from '@/stores/uiStore';

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

// Open-modal stack: ids grow with open order, so the largest open id is the
// visually topmost modal (portals append in open order) and only it consumes
// Escape. Ids are handed out when the modal opens, never at mount time —
// an app-level host (ConfirmDialogHost) mounts before page modals but must
// not pin a low id forever.
let modalSeq = 0;
const openModalIds = new Set<number>();

export function ModalOverlay({ open, onClose, className, children }: ModalOverlayProps) {
  // `seenOpen` keeps the first enter from being treated as an exit; `leaving`
  // holds the overlay mounted for the exit animation before it unmounts.
  const seenOpen = useRef(open);
  const [leaving, setLeaving] = useState(false);
  // Scrim-click close requires press AND release on the scrim itself: a text
  // selection that starts inside the dialog and ends on the scrim targets its
  // click at the common ancestor (the overlay root) and must not close.
  const scrimPressed = useRef(false);
  // This open spell's stack id. Registration is keyed on `open` only: callers
  // pass inline onClose closures, so keying registration on it too would
  // re-register on every parent re-render (streaming updates are constant
  // while dialogs sit open) — the fresh, larger id would steal topmost from a
  // modal opened above this one and Escape would close the wrong layer.
  const stackIdRef = useRef(0);

  if (open) seenOpen.current = true;

  useEffect(() => {
    if (open) {
      // Re-open during the exit window (confirm supersede, fast toggle): the
      // deps change already cleared the pending timer via cleanup, but
      // `leaving` would stay true and pin the overlay on is-leaving (the exit
      // animation's final, faded-out frame) forever.
      setLeaving(false);
      return;
    }
    if (seenOpen.current) {
      seenOpen.current = false;
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), MODAL_EXIT_MS);
      return () => window.clearTimeout(timer);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const id = ++modalSeq;
    stackIdRef.current = id;
    openModalIds.add(id);
    useUIStore.getState().pushModal();
    return () => {
      openModalIds.delete(id);
      useUIStore.getState().popModal();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      // Inner Escape consumers (e.g. a rename input cancelling itself) mark
      // the event handled via preventDefault; the modal must not double-close.
      // Layered modals: only the topmost one answers Escape.
      if (
        e.key === 'Escape' &&
        !e.defaultPrevented &&
        Math.max(...openModalIds) === stackIdRef.current
      ) {
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open && !leaving) return null;

  return createPortal(
    <div
      className={`modal-overlay${leaving ? ' is-leaving' : ''}${className ? ` ${className}` : ''}`}
      role="presentation"
      onMouseDown={(e) => {
        scrimPressed.current = e.target === e.currentTarget;
      }}
      onMouseUp={(e) => {
        if (scrimPressed.current && e.target === e.currentTarget) onClose();
      }}
    >
      {children}
    </div>,
    document.body
  );
}
