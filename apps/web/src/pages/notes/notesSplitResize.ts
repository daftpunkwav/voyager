/**
 * @file notesSplitResize
 * @description Workspace drag-resize slice for the notes page: editor/preview split ratio and the TOC width handle.
 *
 * Responsibilities:
 * - Drag the split divider and write the clamped ratio into the UI store
 *   (local update only, not committed to the view)
 * - Drag the TOC width handle, capped at 60% of the workspace, persisting
 *   the width only on pointer-up
 */

import { useRef, type PointerEvent as ReactPointerEvent } from 'react';
import { useNotesUiStore } from './notesUiStore';
import { parseSplitRatio } from './notePrefs';
import { commitNotesTocWidth } from './notesView';

export function useNotesSplitResize() {
  const setSplitRatio = useNotesUiStore((s) => s.setSplitRatio);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const workspaceRef = useRef<HTMLDivElement | null>(null);

  // Editor/preview split divider: writes splitRatio from clientX's position within the canvas (local immediate update only, not committed to the view)
  const onSplitPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onMove = (ev: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      if (rect.width < 80) return;
      setSplitRatio(parseSplitRatio(String((ev.clientX - rect.left) / rect.width)));
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  // TOC width handle: right edge to clientX, capped at 60% of the width; persisted only on pointer-up
  const onTocPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    const root = workspaceRef.current;
    if (!root) return;
    const onMove = (ev: PointerEvent) => {
      const rect = root.getBoundingClientRect();
      if (rect.width < 80) return;
      const cap = Math.floor(rect.width * 0.6);
      commitNotesTocWidth(Math.min(rect.right - ev.clientX, cap), false);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      commitNotesTocWidth(useNotesUiStore.getState().tocWidth, true);
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return { canvasRef, workspaceRef, onSplitPointerDown, onTocPointerDown };
}
