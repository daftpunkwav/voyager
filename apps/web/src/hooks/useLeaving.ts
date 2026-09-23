/**
 * @file useLeaving
 * @description Shared exit-animation lifecycle for floating surfaces (modals,
 * popovers, lightbox, panels): the element stays mounted with `leaving=true`
 * for `exitMs` after `open` turns false, so the CSS exit animation plays
 * before unmount.
 *
 * - The first mount never plays the exit (nothing to fade out yet)
 * - Re-opening during the exit window cancels the pending timer (via effect
 *   cleanup) and clears `leaving`, so the element never sticks on the final,
 *   faded-out frame
 *
 * Keep each caller's `exitMs` in sync with its `--*-out` CSS duration.
 */

import { useEffect, useRef, useState } from 'react';

export function useLeaving(open: boolean, exitMs: number): boolean {
  // `seenOpen` keeps the first mount from being treated as an exit.
  const seenOpen = useRef(open);
  const [leaving, setLeaving] = useState(false);

  if (open) seenOpen.current = true;

  useEffect(() => {
    if (open) {
      // Re-open during the exit window (fast toggle, supersede): the deps
      // change already cleared the pending timer via cleanup, but `leaving`
      // would stay true and pin the element on is-leaving forever.
      setLeaving(false);
      return;
    }
    if (seenOpen.current) {
      seenOpen.current = false;
      setLeaving(true);
      const timer = window.setTimeout(() => setLeaving(false), exitMs);
      return () => window.clearTimeout(timer);
    }
  }, [open, exitMs]);

  return leaving;
}
