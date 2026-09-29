/**
 * @file notesAutoSave
 * @description Autosave slice for the note editor: dirty tracking, a settings-driven debounced flush (notes.editor.autosave_s, 0=off), a beforeunload beacon fallback, and manual save.
 *
 * The content state itself stays in noteStore; this hook only decides when to
 * persist and to which endpoint.
 *
 * Responsibilities:
 * - Track dirty state against the last persisted snapshot with a debounced
 *   flush driven by notes.editor.autosave_s (0 = off)
 * - Create or update via the notes hooks, reporting save state to the
 *   workspace
 * - Flush on unload through the beacon channel and refuse navigation on
 *   failed saves (empty title or request failure)
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { beaconCapability, callCapability } from '@/bridge/client';
import { EventType } from '@/bridge/events';
import { subscribe } from '@/bridge/stream';
import { i18n } from '@/i18n';
import { useCreateNote, useUpdateNote } from '@/hooks/useNotes';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';
import { isPersistedNoteId } from './noteLine';

export type NotesSaveState = 'saved' | 'unsaved' | 'saving';

/** Debounce source of truth: the notes.editor.autosave_s setting (0=off);
 *  this hook only mirrors it in milliseconds. */
const AUTOSAVE_KEY = 'notes.editor.autosave_s';
const AUTOSAVE_DEFAULT_MS = 5000;

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
  // Debounce width mirrors the notes.editor.autosave_s setting (0=off: no
  // timer is armed, manual save / the unload beacon stay available). A live
  // save already in flight keeps its old delay — the new value applies from
  // the next dirty mark.
  const [autosaveMs, setAutosaveMs] = useState(AUTOSAVE_DEFAULT_MS);
  useEffect(() => {
    let alive = true;
    // Set once a settings.changed event has been applied: the in-flight
    // initial read may still carry the pre-change value and must not win
    let eventApplied = false;
    const apply = (seconds: number) => {
      if (alive) setAutosaveMs(seconds > 0 ? seconds * 1000 : 0);
    };
    callCapability<{ value?: number }>('settings', 'get_setting', { key: AUTOSAVE_KEY })
      .then((item) => {
        if (alive && !eventApplied) apply(Number(item?.value ?? AUTOSAVE_DEFAULT_MS / 1000));
      })
      .catch(() => {
        // Settings unreadable (backend down): keep the default debounce
      });
    const off = subscribe([EventType.SETTINGS_CHANGED], (event) => {
      const payload = event.payload as { key?: string; value?: unknown };
      if (payload.key === AUTOSAVE_KEY) {
        eventApplied = true;
        apply(Number(payload.value ?? AUTOSAVE_DEFAULT_MS / 1000));
      }
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  /** Shared settle tail after a save resolves: apply the clean/dirty verdict
   *  (dirty flag + save state) and re-arm the debounce when keystrokes landed
   *  during the in-flight request — they must stay dirty or they would be
   *  silently dropped behind a "saved" indicator (including on beforeunload,
   *  which reads the same dirty flag). Returns the verdict; callers must
   *  propagate it before navigating away or promoting the URL. */
  const settleAfterSave = useCallback(
    (clean: boolean): boolean => {
      dirtyRef.current = !clean;
      setSaveState(clean ? 'saved' : 'unsaved');
      if (!clean && !timerRef.current && autosaveMs > 0) {
        timerRef.current = setTimeout(() => void flushRef.current(), autosaveMs);
      }
      return clean;
    },
    [autosaveMs]
  );

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
        // Clear dirty only when the editor still holds exactly what was just
        // persisted (id included: the editor may have switched notes while
        // the request was in flight). Keystrokes that landed during the
        // in-flight save must stay dirty (and re-arm), or they would be
        // silently dropped behind a "saved" indicator — including on
        // beforeunload, which reads the same dirty flag.
        const cur = useNoteStore.getState();
        return settleAfterSave(
          cur.editingNoteId === id && cur.editorTitle === t && cur.editorContent === c
        );
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
      const saved = {
        id: created.id,
        title: created.title ?? t,
        content: created.content ?? c,
      };
      lastPersistedRef.current = saved;
      // Same in-flight guard via settleAfterSave: keystrokes that landed
      // while the create request was running must stay dirty (and re-arm),
      // or the note=<id> promotion below would silently mark them saved
      // behind a clean dirty flag. The editor id is not compared here: it
      // has not switched yet at this point (the URL sync happens in the
      // setSearchParams below), so title/content decide.
      const cur = useNoteStore.getState();
      const clean = cur.editorTitle === saved.title && cur.editorContent === saved.content;
      const settled = settleAfterSave(clean);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('note', created.id);
          next.delete('open');
          return next;
        },
        { replace: true }
      );
      return settled;
    } catch (err) {
      setSaveState('unsaved');
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : i18n.t('notes:save.failed'),
      });
      return false;
    }
  }, [updateNote, createNote, newProjectId, addToast, setSearchParams, settleAfterSave]);

  /** Marks dirty and resets the debounce timer (autosave_s=0 arms nothing). */
  const markDirty = useCallback(() => {
    dirtyRef.current = true;
    setSaveState('unsaved');
    if (timerRef.current) clearTimeout(timerRef.current);
    if (autosaveMs > 0) timerRef.current = setTimeout(() => void flush(), autosaveMs);
  }, [flush, autosaveMs]);

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
