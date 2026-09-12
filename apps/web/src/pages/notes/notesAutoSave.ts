/**
 * @file notesAutoSave
 * @description Autosave slice for the note editor: dirty tracking, a 5s debounced flush, a beforeunload beacon fallback, and manual save.
 *
 * The content state itself stays in noteStore; this hook only decides when to
 * persist and to which endpoint.
 *
 * Responsibilities:
 * - Track dirty state against the last persisted snapshot with a 5s
 *   debounced flush
 * - Create or update via the notes hooks, reporting save state to the
 *   workspace
 * - Flush on unload through the beacon channel and refuse navigation on
 *   failed saves (empty title or request failure)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { beaconCapability } from '@/bridge/client';
import { i18n } from '@/i18n';
import { useCreateNote, useUpdateNote } from '@/hooks/useNotes';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';
import { isPersistedNoteId } from './noteLine';

export type NotesSaveState = 'saved' | 'unsaved' | 'saving';

/** The project id attached when a new draft is persisted is owned by the page (the workspace also displays it); the hook only consumes it. */
export function useNotesAutoSave(options: { newProjectId: string }) {
  const { newProjectId } = options;
  const [, setSearchParams] = useSearchParams();
  const updateNote = useUpdateNote();
  const createNote = useCreateNote();
  const addToast = useUIStore((s) => s.addToast);
  const editorContent = useNoteStore((s) => s.editorContent);
  const editorTitle = useNoteStore((s) => s.editorTitle);
  const editingNoteId = useNoteStore((s) => s.editingNoteId);
  const [saveState, setSaveState] = useState<NotesSaveState>('saved');
  const dirtyRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPersistedRef = useRef<{ id: string; title: string; content: string } | null>(null);

  /** Persists dirty content immediately (or creates the draft); a clean state passes through untouched.
   *  Returns false when there are real changes that could not be saved (empty title or save failure):
   *  callers must check the return value before navigating away or overwriting and abort on failure —
   *  never silently discard a draft. */
  const flush = useCallback(async (): Promise<boolean> => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    if (!dirtyRef.current) return true;
    const id = useNoteStore.getState().editingNoteId;
    const t = useNoteStore.getState().editorTitle;
    const c = useNoteStore.getState().editorContent;
    if (!t.trim()) {
      // An empty title cannot create/update; only equal-to-persisted-snapshot (or an empty draft body) counts as losing nothing
      const baseline = lastPersistedRef.current;
      const unchanged = baseline
        ? baseline.id === id && baseline.title === t && baseline.content === c
        : !c.trim();
      if (unchanged) {
        dirtyRef.current = false;
        setSaveState('saved');
        return true;
      }
      setSaveState('unsaved');
      addToast({ type: 'warning', message: i18n.t('notes:autosave.emptyTitle') });
      return false;
    }
    if (isPersistedNoteId(id)) {
      if (
        lastPersistedRef.current?.id === id &&
        lastPersistedRef.current?.title === t &&
        lastPersistedRef.current?.content === c
      ) {
        dirtyRef.current = false;
        setSaveState('saved');
        return true;
      }
      setSaveState('saving');
      try {
        await updateNote.mutateAsync({ id, title: t, content: c });
        lastPersistedRef.current = { id, title: t, content: c };
        dirtyRef.current = false;
        setSaveState('saved');
        return true;
      } catch (err) {
        setSaveState('unsaved');
        addToast({
          type: 'error',
          message: err instanceof Error ? err.message : i18n.t('notes:save.failed'),
        });
        return false;
      }
    }
    setSaveState('saving');
    try {
      const created = await createNote.mutateAsync({
        projectId: newProjectId || '',
        title: t,
        content: c,
      });
      lastPersistedRef.current = {
        id: created.id,
        title: created.title ?? t,
        content: created.content ?? c,
      };
      dirtyRef.current = false;
      setSaveState('saved');
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('note', created.id);
          next.delete('open');
          return next;
        },
        { replace: true }
      );
      return true;
    } catch (err) {
      setSaveState('unsaved');
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : i18n.t('notes:save.failed'),
      });
      return false;
    }
  }, [updateNote, createNote, newProjectId, addToast, setSearchParams]);

  /** Marks dirty and resets the 5s debounce timer. */
  const markDirty = useCallback(() => {
    dirtyRef.current = true;
    setSaveState('unsaved');
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => void flush(), 5000);
  }, [flush]);

  // Content change marks dirty; skip the very first change right after a note is loaded (loadedFor tracks which note has been loaded)
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (loadedFor.current !== editingNoteId) {
      loadedFor.current = editingNoteId;
      return;
    }
    const last = lastPersistedRef.current;
    if (
      isPersistedNoteId(editingNoteId) &&
      last &&
      last.id === editingNoteId &&
      last.title === editorTitle &&
      last.content === editorContent
    ) {
      return;
    }
    markDirty();
  }, [editorContent, editorTitle, editingNoteId, markDirty]);

  // Fallback for dirty changes via sendBeacon before the page closes; clears the debounce timer on unmount
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      const id = useNoteStore.getState().editingNoteId;
      const t = useNoteStore.getState().editorTitle;
      const c = useNoteStore.getState().editorContent;
      if (isPersistedNoteId(id) && t.trim()) {
        beaconCapability(
          'notes',
          'update_note',
          JSON.stringify({ note_id: id, title: t, content: c })
        );
      }
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // Lets non-reactive flows (URL opens / note switches) reach the latest flush
  const flushRef = useRef(flush);
  flushRef.current = flush;

  /** Toolbar "save": warns on an empty title; otherwise forces dirty and flushes immediately. */
  const handleSave = async () => {
    if (!useNoteStore.getState().editorTitle.trim()) {
      addToast({ type: 'warning', message: i18n.t('notes:save.emptyTitle') });
      return;
    }
    dirtyRef.current = true;
    await flush();
  };

  return {
    saveState,
    setSaveState,
    dirtyRef,
    lastPersistedRef,
    flush,
    flushRef,
    handleSave,
    // Mutation state shared with flush, for the workspace "saving" indicator
    saving: updateNote.isPending || createNote.isPending,
  };
}
