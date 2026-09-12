/**
 * @file notesOpenNote
 * @description Note open/create lifecycle: URL ?note= driven loading, alignment with remote note.edited events, and the create entry point.
 *
 * Responsibilities:
 * - Drive the workspace from the ?note= URL param (legacy ?open=
 *   accepted), flushing unsaved work before switching
 * - Load full note bodies via fetchNoteFull and track the persisted
 *   snapshot, opening flag, and meta (pinned/archived)
 * - Subscribe to note.edited so remote edits refresh the open note
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchNoteFull } from '@/hooks/useNotes';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from './notesUiStore';
import { useUIStore } from '@/stores/uiStore';
import { routes } from '@/utils/routes';
import { i18n } from '@/i18n';
import { subscribe } from '@/bridge/stream';
import { noteSourceId } from './noteListing';
import type { NotesSaveState } from './notesAutoSave';

/** Reads the note id to open from the URL (?note= or the legacy ?open=); 'new' means a fresh draft. */
export function noteQueryId(params: URLSearchParams): string | null {
  return params.get('note') ?? params.get('open');
}

interface NotesMeta {
  pinned: boolean;
  archived: boolean;
}

interface UseNotesOpenerOptions {
  /** Latest flush reference from the autosave hook (flush before switching away / opening; false = could not persist, must abort the overwrite). */
  flushRef: { current: () => Promise<boolean> };
  lastPersistedRef: { current: { id: string; title: string; content: string } | null };
  dirtyRef: { current: boolean };
  setSaveState: (state: NotesSaveState) => void;
  setNewProjectId: (id: string) => void;
}

/** Open/create slice: the opening flag and meta state live here; the page only consumes them. */
export function useNotesOpener(options: UseNotesOpenerOptions) {
  const { flushRef, lastPersistedRef, dirtyRef, setSaveState, setNewProjectId } = options;
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const startEditing = useNoteStore((s) => s.startEditing);
  const sourceId = useNotesUiStore((s) => s.sourceId);
  const [opening, setOpening] = useState(false);
  const [meta, setMeta] = useState<NotesMeta>({ pinned: false, archived: false });
  const noteSeqRef = useRef(0);

  // Driven by URL ?note=: flush before switching away; opens via fetchNoteFull and records the persisted snapshot
  useEffect(() => {
    const noteId = noteQueryId(searchParams);
    let cancelled = false;

    const run = async () => {
      if (!noteId) {
        if (!(await flushRef.current())) return; // not persisted: keep the editing state, do not clear the workspace
        if (cancelled) return;
        const still = noteQueryId(new URLSearchParams(window.location.search));
        if (!still) useNoteStore.getState().stopEditing();
        return;
      }
      if (noteId === 'new') {
        if (useNoteStore.getState().editingNoteId !== 'new') {
          if (!(await flushRef.current())) return; // not persisted: do not interrupt the current draft
          if (cancelled) return;
          startEditing('new', i18n.t('notes:newNote'), '');
          setNewProjectId(searchParams.get('project') || '');
          lastPersistedRef.current = null;
          dirtyRef.current = false;
          setSaveState('unsaved');
          setMeta({ pinned: false, archived: false });
        }
        return;
      }
      if (useNoteStore.getState().editingNoteId === noteId) return;
      if (!(await flushRef.current())) return; // not persisted: do not load a new note over the current content
      if (cancelled) return;
      const seq = ++noteSeqRef.current;
      setOpening(true);
      try {
        const full = await fetchNoteFull(noteId);
        if (cancelled || seq !== noteSeqRef.current) return;
        startEditing(full.id, full.title, full.content);
        setNewProjectId(noteSourceId(full));
        lastPersistedRef.current = { id: full.id, title: full.title, content: full.content };
        dirtyRef.current = false;
        setSaveState('saved');
        setMeta({ pinned: Boolean(full.pinned), archived: Boolean(full.archived) });
      } catch (err) {
        addToast({
          type: 'error',
          message: err instanceof Error ? err.message : i18n.t('notes:openNote.failed'),
        });
        if (!cancelled) navigate(routes.notes, { replace: true });
      } finally {
        if (seq === noteSeqRef.current) setOpening(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
    // refs and setState setters are stable and do not re-trigger the effect
  }, [
    searchParams,
    startEditing,
    addToast,
    navigate,
    flushRef,
    lastPersistedRef,
    dirtyRef,
    setSaveState,
    setNewProjectId,
  ]);

  // Remote note.edited: pull the full note to align when the local copy is clean (a dirty local edit is never interrupted)
  useEffect(() => {
    return subscribe(['note.edited'], (event) => {
      const nid = event.payload.note_id;
      if (typeof nid !== 'string' || nid !== useNoteStore.getState().editingNoteId) return;
      if (dirtyRef.current) return;
      void fetchNoteFull(nid)
        .then((full) => {
          const s = useNoteStore.getState();
          if (dirtyRef.current || s.editingNoteId !== nid) return;
          if (s.editorTitle === full.title && s.editorContent === full.content) return;
          startEditing(full.id, full.title, full.content);
          lastPersistedRef.current = { id: full.id, title: full.title, content: full.content };
          setNewProjectId(noteSourceId(full));
          setMeta({ pinned: Boolean(full.pinned), archived: Boolean(full.archived) });
        })
        .catch(() => {
          /* Remote change could not be fetched locally; invalidating the list keeps the next open aligned */
        });
    });
  }, [startEditing, dirtyRef, lastPersistedRef, setNewProjectId]);

  /** List/workspace "new" action: resets the draft when already on ?note=new, otherwise navigates there carrying the project. */
  const handleNew = async () => {
    if (!(await flushRef.current())) return; // not persisted: do not reset the current edit
    const project = searchParams.get('project') || sourceId || '';
    if (noteQueryId(searchParams) === 'new') {
      startEditing('new', i18n.t('notes:newNote'), '');
      setNewProjectId(project);
      lastPersistedRef.current = null;
      dirtyRef.current = false;
      setSaveState('unsaved');
      setMeta({ pinned: false, archived: false });
      return;
    }
    navigate(routes.note('new', project || undefined));
  };

  return { opening, meta, setMeta, handleNew };
}
