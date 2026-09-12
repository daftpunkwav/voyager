/**
 * @file notesSplitScroll
 * @description Split-pane scroll sync for the notes workspace plus TOC navigation; holds the editor/preview DOM handles.
 *
 * Responsibilities:
 * - Bind bidirectional scroll sync in split mode with an rAF event lock
 *   to prevent write-back storms
 * - Hold the editor/preview DOM handles and run TOC jumps (editor line
 *   jump plus smooth preview scroll)
 */

import { useCallback, useEffect, useState } from 'react';
import { type NoteEditorHandle } from './NoteEditor';
import { syncScrollRatio } from './noteLine';
import type { NoteTocItem } from './noteOutline';
import { useNotesUiStore } from './notesUiStore';

export function useNotesSplitScroll() {
  const mode = useNotesUiStore((s) => s.mode);
  const syncScroll = useNotesUiStore((s) => s.syncScroll);
  const [editorApi, setEditorApi] = useState<NoteEditorHandle | null>(null);
  const [previewEl, setPreviewEl] = useState<HTMLDivElement | null>(null);

  // Split mode bidirectional scroll sync: an event lock released on rAF prevents write-back storms
  useEffect(() => {
    if (mode !== 'split' || !syncScroll) return;
    const a = editorApi?.scrollDom;
    const b = previewEl;
    if (!a || !b) return;
    let lock = false;
    const bind = (from: HTMLElement, to: HTMLElement) => () => {
      if (lock) return;
      lock = true;
      syncScrollRatio(from, to);
      requestAnimationFrame(() => {
        lock = false;
      });
    };
    const onA = bind(a, b);
    const onB = bind(b, a);
    a.addEventListener('scroll', onA, { passive: true });
    b.addEventListener('scroll', onB, { passive: true });
    return () => {
      a.removeEventListener('scroll', onA);
      b.removeEventListener('scroll', onB);
    };
  }, [mode, syncScroll, editorApi, previewEl]);

  /** TOC click: jumps to the line in edit mode; in preview/split also smooth-scrolls to the matching heading. */
  const jumpToc = useCallback(
    (item: NoteTocItem, headingId: string) => {
      if (mode !== 'preview') editorApi?.goToLine(item.line);
      if (mode === 'edit') return;
      const el = document.getElementById(headingId);
      if (el && previewEl?.contains(el)) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    },
    [mode, editorApi, previewEl]
  );

  return { editorApi, setEditorApi, previewEl, setPreviewEl, jumpToc };
}
