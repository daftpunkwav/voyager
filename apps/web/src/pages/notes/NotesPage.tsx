/**
 * @file NotesPage
 * @description Notes coordination page: assembles the listing / workspace and wires page-level props only.
 *
 * Behavior slices live in sibling modules: autosave (notesAutoSave),
 * open/create (notesOpenNote), drag-resize (notesSplitResize), batch
 * operations (notesBatch), and drawers (NotesDrawers).
 *
 * Responsibilities:
 * - Assemble the listing / workspace branches from the ?note= URL param
 * - Hold page-level wiring: pin/archive/link mutations, export, assist
 *   entry, and TOC extraction
 * - Persist every preference change through the notes view pipeline
 * - Publish the loaded list count to the page probe provider
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAllNotes, useLinkNote, usePatchNoteMeta } from '@/hooks/useNotes';
import { useProjects } from '@/hooks/useProjects';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesUiStore } from './notesUiStore';
import { useUIStore } from '@/stores/uiStore';
import { exportNote } from '@/api/notes';
import { routes } from '@/utils/routes';
import { openFloatingChat } from '@/bridge/chatSend';
import type { Note } from '@/api/types';
import { NoteIndex } from './NoteIndex';
import { NotesWorkspace } from './NotesWorkspace';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import {
  bumpNotesFont,
  commitNotesDensity,
  commitNotesFilter,
  commitNotesLayout,
  commitNotesListState,
  commitNotesMode,
  commitNotesPanel,
  commitNotesQuery,
  commitNotesSort,
  commitNotesSourceId,
  commitNotesSyncScroll,
  commitNotesTocWidth,
  openNotesAssist,
} from './notesView';
import { isPersistedNoteId } from './noteLine';
import { rememberNotesListCount } from './provider';
import { extractNoteToc } from './noteOutline';
import { useNotesAutoSave } from './notesAutoSave';
import { useNotesOpener, noteQueryId } from './notesOpenNote';
import { useNotesSplitResize } from './notesSplitResize';
import { useNotesSplitScroll } from './notesSplitScroll';
import { useNotesBatch } from './notesBatch';
import { NotesDrawers } from './NotesDrawers';

export function NotesPage() {
  const { t } = useTranslation('notes');
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const noteParam = noteQueryId(searchParams);
  const isWorkspace = Boolean(noteParam);
  const listState = useNotesUiStore((s) => s.listState);
  const layout = useNotesUiStore((s) => s.layout);
  const mode = useNotesUiStore((s) => s.mode);
  const fontSize = useNotesUiStore((s) => s.fontSize);
  const syncScroll = useNotesUiStore((s) => s.syncScroll);
  const splitRatio = useNotesUiStore((s) => s.splitRatio);
  const tocWidth = useNotesUiStore((s) => s.tocWidth);
  const query = useNotesUiStore((s) => s.query);
  const sort = useNotesUiStore((s) => s.sort);
  const filter = useNotesUiStore((s) => s.filter);
  const sourceId = useNotesUiStore((s) => s.sourceId);
  const panel = useNotesUiStore((s) => s.panel);
  const density = useNotesUiStore((s) => s.density);
  const { data: notes = [], isLoading } = useAllNotes(listState);
  const { data: projectsData } = useProjects();
  // Publish the list count to the page probe provider once data arrives; skip while loading to avoid reporting a fake 0
  useEffect(() => {
    if (!isLoading) rememberNotesListCount(notes.length);
  }, [notes.length, isLoading]);
  const editorContent = useNoteStore((s) => s.editorContent);
  const editorTitle = useNoteStore((s) => s.editorTitle);
  const editingNoteId = useNoteStore((s) => s.editingNoteId);
  const linkNote = useLinkNote();
  const patchMeta = usePatchNoteMeta();
  const addToast = useUIStore((s) => s.addToast);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newProjectId, setNewProjectId] = useState(() => searchParams.get('project') ?? '');
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [formatBarHost, setFormatBarHost] = useState<HTMLDivElement | null>(null);
  const [editMounted, setEditMounted] = useState(false);
  const [previewMounted, setPreviewMounted] = useState(false);
  const [previewBody, setPreviewBody] = useState('');
  const [tocOpen, setTocOpen] = useState(true);

  // Behavior slices: autosave / open & create / split drag-resize / list batch ops
  const {
    saveState,
    setSaveState,
    dirtyRef,
    lastPersistedRef,
    flush,
    flushRef,
    handleSave,
    saving,
  } = useNotesAutoSave({ newProjectId });
  const { opening, meta, setMeta, handleNew } = useNotesOpener({
    flushRef,
    lastPersistedRef,
    dirtyRef,
    setSaveState,
    setNewProjectId,
  });
  const { canvasRef, workspaceRef, onSplitPointerDown, onTocPointerDown } = useNotesSplitResize();
  const { runBatch, batchPending } = useNotesBatch();
  // Split scroll sync and TOC navigation (holds the editor/preview DOM handles)
  const { setEditorApi, setPreviewEl, jumpToc } = useNotesSplitScroll();

  useEffect(() => {
    if (noteQueryId(searchParams)) return;
    const fromUrl = searchParams.get('project');
    if (fromUrl) commitNotesSourceId(fromUrl);
    // Consume the URL only on landing; notes.ui.source_id takes over afterwards
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const projectNames = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of projectsData?.items ?? []) {
      m.set(p.id, p.name);
    }
    return m;
  }, [projectsData]);

  const projectOptions = useMemo(
    () => (projectsData?.items ?? []).map((p) => ({ value: p.id, label: p.name })),
    [projectsData]
  );

  const goIndex = useCallback(async () => {
    if (!(await flush())) return; // not persisted: stay in the workspace, the toast was raised by flush
    navigate(routes.notes);
  }, [flush, navigate]);

  const openNote = useCallback(
    async (n: Note) => {
      if (!(await flush())) return; // not persisted: do not switch away and overwrite the current content
      navigate(routes.note(n.id));
    },
    [flush, navigate]
  );

  const handleProjectChange = async (value: string) => {
    setNewProjectId(value);
    if (!isPersistedNoteId(editingNoteId)) return;
    try {
      await linkNote.mutateAsync({ id: editingNoteId, sourceId: value || null });
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('notes:page.linkProjectFailed'),
      });
    }
  };

  const handlePin = async (note: Note, pinned: boolean) => {
    try {
      await patchMeta.mutateAsync({ id: note.id, pinned });
      if (note.id === editingNoteId) setMeta((m) => ({ ...m, pinned }));
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('notes:page.pinFailed'),
      });
    }
  };

  const togglePinCurrent = () => {
    if (!isPersistedNoteId(editingNoteId)) return;
    void handlePin({ id: editingNoteId } as Note, !meta.pinned);
  };

  const toggleArchiveCurrent = async () => {
    if (!isPersistedNoteId(editingNoteId)) return;
    const archived = !meta.archived;
    try {
      await patchMeta.mutateAsync({ id: editingNoteId, archived });
      setMeta((m) => ({ ...m, archived }));
      if (archived && (await flush())) {
        navigate(routes.notes);
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('notes:page.archiveFailed'),
      });
    }
  };

  const openAssist = () => {
    openFloatingChat();
    openNotesAssist();
  };

  useEffect(() => {
    if (!isWorkspace) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === '=' || e.key === '+' || e.key === '-')) {
        e.preventDefault();
        bumpNotesFont(e.key === '-' ? -1 : 1);
        return;
      }
      if (e.key !== 'Escape') return;
      // Yield to global modals (lightbox etc.): one Esc closes only the topmost modal
      if (useUIStore.getState().modalDepth > 0) return;
      if (deleteOpen || versionsOpen || panel === 'trash') return;
      if (document.querySelector('.glass-select.is-open')) return;
      e.preventDefault();
      void goIndex();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isWorkspace, deleteOpen, versionsOpen, panel, goIndex]);

  useEffect(() => {
    if (!isWorkspace) {
      setEditMounted(false);
      setPreviewMounted(false);
      return;
    }
    const ready = noteParam === 'new' || editingNoteId === noteParam;
    if (opening && !ready) return;
    if (mode !== 'preview') setEditMounted(true);
    if (mode !== 'edit') setPreviewMounted(true);
  }, [isWorkspace, noteParam, editingNoteId, opening, mode]);

  useEffect(() => {
    if (mode === 'edit') return;
    if (mode === 'preview') {
      setPreviewBody(editorContent);
      return;
    }
    const timer = window.setTimeout(() => setPreviewBody(editorContent), 280);
    return () => window.clearTimeout(timer);
  }, [editorContent, mode]);

  const showEdit = mode === 'edit' || mode === 'split';
  const persisted = isPersistedNoteId(editingNoteId);
  const tocItems = useMemo(() => extractNoteToc(editorContent), [editorContent]);

  if (!isWorkspace && isLoading && notes.length === 0) return <LoadingSpinner fullScreen />;

  const drawers = (
    <NotesDrawers
      persisted={persisted}
      editingNoteId={editingNoteId ?? ''}
      versionsOpen={versionsOpen}
      onCloseVersions={() => setVersionsOpen(false)}
      trashOpen={panel === 'trash'}
      deleteOpen={deleteOpen}
      onCloseDelete={() => setDeleteOpen(false)}
    />
  );

  if (!isWorkspace) {
    return (
      <>
        <NoteIndex
          notes={notes}
          empty={notes.length === 0}
          layout={layout}
          listState={listState}
          onLayoutChange={commitNotesLayout}
          onListStateChange={commitNotesListState}
          query={query}
          onQuery={commitNotesQuery}
          sort={sort}
          onSort={commitNotesSort}
          filter={filter}
          onFilter={commitNotesFilter}
          sourceId={sourceId}
          onSourceId={commitNotesSourceId}
          density={density}
          onDensity={commitNotesDensity}
          projectOptions={projectOptions}
          projectNames={projectNames}
          onOpen={(n) => void openNote(n)}
          onNew={() => void handleNew()}
          onTrash={() => commitNotesPanel('trash')}
          onAssist={openAssist}
          onPin={(n, pinned) => void handlePin(n, pinned)}
          onArchive={(ids, archived) => void runBatch(ids, archived ? 'archive' : 'unarchive')}
          onExport={(ids) => void runBatch(ids, 'export')}
          onDelete={(ids) => void runBatch(ids, 'delete')}
          busy={batchPending}
        />
        {drawers}
      </>
    );
  }

  const workspaceReady = noteParam === 'new' || editingNoteId === noteParam;

  return (
    <NotesWorkspace
      fontSize={fontSize}
      mode={mode}
      saveState={saveState}
      persisted={persisted}
      pinned={meta.pinned}
      archived={meta.archived}
      projectId={newProjectId}
      projectOptions={projectOptions}
      syncScroll={syncScroll}
      tocOpen={tocOpen}
      tocItems={tocItems}
      tocWidth={tocWidth}
      splitRatio={splitRatio}
      showEdit={showEdit}
      opening={opening}
      workspaceReady={workspaceReady}
      editMounted={editMounted}
      previewMounted={previewMounted}
      editorTitle={editorTitle}
      previewBody={previewBody}
      editingNoteId={editingNoteId}
      formatBarHost={formatBarHost}
      saving={saving}
      overlays={drawers}
      canvasRef={canvasRef}
      workspaceRef={workspaceRef}
      onFormatBarHost={setFormatBarHost}
      onEditorReady={setEditorApi}
      onPreviewEl={setPreviewEl}
      onSplitPointerDown={onSplitPointerDown}
      onTocPointerDown={onTocPointerDown}
      onTocWidth={commitNotesTocWidth}
      onJumpToc={jumpToc}
      onBack={() => void goIndex()}
      onNew={() => void handleNew()}
      onMode={commitNotesMode}
      onBumpFont={bumpNotesFont}
      onProject={(v) => void handleProjectChange(v)}
      onTogglePin={togglePinCurrent}
      onToggleArchive={() => void toggleArchiveCurrent()}
      onToggleSync={() => commitNotesSyncScroll(!syncScroll)}
      onToggleToc={() => setTocOpen((v) => !v)}
      onAssist={openAssist}
      onVersions={() => setVersionsOpen(true)}
      onExport={() => {
        if (!persisted) return;
        void exportNote(editingNoteId)
          .then((res) => {
            addToast({
              type: 'success',
              message: t('notes:exportedPath', { path: (res as { path: string }).path }),
            });
          })
          .catch((err: unknown) => {
            addToast({
              type: 'error',
              message: err instanceof Error ? err.message : t('notes:page.exportFailed'),
            });
          });
      }}
      onDelete={() => setDeleteOpen(true)}
      onTrash={() => commitNotesPanel('trash')}
      onSave={() => void handleSave()}
    />
  );
}
