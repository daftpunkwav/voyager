/**
 * @file Popover
 * @description Shared anchored-popover lifecycle for non-modal floating
 * surfaces (composer dropdowns, context ring, sidebar session menu, display
 * panels): outside-click and Escape close it, and the exit animation plays
 * before the content unmounts. Exit is faster than enter, and the panel grows
 * from the edge facing the trigger (direction), so the popover feels anchored
 * to its trigger instead of appearing from nowhere.
 *
 * The caller owns positioning (absolute CSS against its own anchor) and the
 * glass material classes; this component owns only the open/leaving behavior
 * and the motion classes.
 */

import { useEffect, useRef, useState } from 'react';

interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** The anchor root: mousedowns inside it (trigger included) never close the popover */
  anchorRef: React.RefObject<HTMLElement | null>;
  /** Which side of the trigger the panel floats on; sets the grow origin */
  direction?: 'up' | 'down';
  /** Positioning + material classes for the panel (caller-owned CSS) */
  className?: string;
  /** ARIA role for the panel surface (listbox, dialog, menu...) */
  role?: string;
  /** Accessible name when role is a dialog/menu */
  ariaLabel?: string;
  /**
   * Panel content. A function form is a lazy render prop: it is only invoked
   * while the popover is visible (enter or exit), so callers may safely read
   * data that only exists when open.
   */
  children: React.ReactNode | (() => React.ReactNode);
}

/** Keep in sync with --popover-out in global.css. Faster than the 150ms enter. */
export const POPOVER_EXIT_MS = 120;

export function Popover({
  open,
  onClose,
  anchorRef,
  direction = 'up',
  className,
  role,
  ariaLabel,
  children,
}: PopoverProps) {
  // `seenOpen` keeps the first mount from playing the exit; `leaving` holds
  // the panel mounted through the exit animation before it unmounts.
  const seenOpen = useRef(open);
  const [leaving, setLeaving] = useState(false);

  if (open) seenOpen.current = true;

  useEffect(() => {
    if (!open && seenOpen.current) {
      seenOpen.current = false;
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), POPOVER_EXIT_MS);
      return () => window.clearTimeout(timer);
    }
  }, [open]);

  const active = open || leaving;

  useEffect(() => {
    if (!active) return;
    const onDown = (e: MouseEvent) => {
      if (!anchorRef.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !e.defaultPrevented) onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [active, anchorRef, onClose]);

  if (!active) return null;

  // Lazy render props evaluate only now: never while closed, still rendered
  // through the exit animation.
  const content = typeof children === 'function' ? children() : children;

  return (
    <div
      role={role}
      aria-label={ariaLabel}
      className={[
        'popover-pop',
        `popover-pop--${direction}`,
        leaving ? 'is-leaving' : '',
        className ?? '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {content}
    </div>
  );
}
