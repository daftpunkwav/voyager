/**
 * @file useNotes
 * @description Notes-domain data hooks: CRUD plus trash, versions, tags, TOC,
 * backlinks, export and batch operations.
 *
 * Responsibilities:
 * - Provide note list/search/detail queries and CRUD mutations with notes
 *   and overview cache invalidation
 * - Serve the extended features: trash restore/purge/empty, versions,
 *   tags, TOC, backlinks, export, and batch actions
 * - Keep the editor store aligned on create/delete/version-restore via
 *   startEditing/stopEditing
 * - Expose fetchNoteFull so openers mount full bodies instead of list
 *   summaries
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listNotes,
  searchNotes,
  getNote,
  createNote,
  updateNote,
  deleteNote,
  listNoteTags,
  getNoteToc,
  getBacklinks,
  restoreNote,
  purgeNote,
  emptyTrash,
  listVersions,
  restoreVersion,
  renameNoteTag,
  linkNote,
  exportNote,
  batchNotes,
} from '@/api/notes';
import type { Note } from '@/api/types';
import { useNoteStore } from '@/stores/noteStore';
import { invalidateOverviewQueries } from '@/utils/invalidateOverview';

export type NotesListView = 'active' | 'archived';

export function useAllNotes(state: NotesListView = 'active') {
  return useQuery({
    queryKey: ['notes', 'all', state],
    queryFn: async () => {
      // Frontend-side filtering for the notes home; anything beyond 200 notes is truncated
      return (await searchNotes('', { state, limit: 200 })) as Note[];
    },
  });
}

export function useProjectNotes(projectId: string | undefined) {
  return useQuery({
    queryKey: ['notes', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('missing projectId');
      return listNotes(projectId);
    },
    enabled: Boolean(projectId),
  });
}

export function useNote(id: string | undefined) {
  return useQuery({
    queryKey: ['note', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return getNote(id);
    },
    enabled: Boolean(id),
  });
}

export function useCreateNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      projectId,
      title,
      content,
    }: {
      projectId: string;
      title: string;
      content: string;
    }) => {
      return createNote(projectId, { title, content });
    },
    onSuccess: (note) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
      useNoteStore.getState().startEditing(note.id, note.title, note.content);
    },
  });
}

export function useUpdateNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, title, content }: { id: string; title: string; content: string }) => {
      return updateNote(id, { title, content });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useDeleteNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await deleteNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
      useNoteStore.getState().stopEditing();
    },
  });
}

export function useLinkNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, sourceId }: { id: string; sourceId: string | null }) => {
      await linkNote(id, sourceId);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

/** Only toggles pinned/archived; title and content untouched (kept off the auto-versioning update path). */
export function usePatchNoteMeta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      pinned,
      archived,
    }: {
      id: string;
      pinned?: boolean;
      archived?: boolean;
    }) => {
      return updateNote(id, { pinned, archived });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

// ---------- Extended features: trash / versions / tags / TOC / backlinks / export / attachments ----------

/** Fetch the full note before opening it (list_notes returns summaries only; mounting a summary would truncate the body). */
export async function fetchNoteFull(id: string): Promise<{
  id: string;
  title: string;
  content: string;
  source_id?: string;
  project_id?: string;
  pinned?: boolean;
  archived?: boolean;
}> {
  return getNote(id);
}

export function useNoteTags() {
  return useQuery({
    queryKey: ['noteTags'],
    queryFn: async () => (await listNoteTags()) as { tag: string; count: number }[],
  });
}

export function useNoteToc(id: string | undefined) {
  return useQuery({
    queryKey: ['noteToc', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await getNoteToc(id)) as {
        toc: { level: number; text: string; line: number }[];
      };
    },
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

export function useBacklinks(id: string | undefined) {
  return useQuery({
    queryKey: ['noteBacklinks', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await getBacklinks(id)) as {
        backlinks: { id: string; title: string; excerpt: string; updated_ts: number }[];
      };
    },
    enabled: Boolean(id),
  });
}

export function useTrashNotes(enabled: boolean) {
  return useQuery({
    queryKey: ['notes', 'trash'],
    queryFn: async () => {
      return (await searchNotes('', { state: 'trash' })) as {
        id: string;
        title: string;
        updated_ts: number;
      }[];
    },
    enabled,
  });
}

export function useRestoreNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await restoreNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function usePurgeNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await purgeNote(id);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function useEmptyTrash() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      await emptyTrash();
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
    },
  });
}

export function useNoteVersions(id: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['noteVersions', id],
    queryFn: async () => {
      if (!id) throw new Error('missing id');
      return (await listVersions(id)) as {
        versions: { version: number; ts: number; chars: number }[];
        current_chars: number;
      };
    },
    enabled: Boolean(id) && enabled,
  });
}

export function useRestoreVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: string; version: number }) => {
      return restoreVersion(input.id, input.version);
    },
    onSuccess: (note) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      const n = note as { id: string; title: string; content: string };
      useNoteStore.getState().startEditing(n.id, n.title, n.content);
    },
  });
}

export function useExportNote() {
  return useMutation({
    mutationFn: async (id: string) => (await exportNote(id)) as { path: string; chars: number },
  });
}

export type NoteBatchAction = 'archive' | 'unarchive' | 'delete' | 'export' | 'pin' | 'unpin';

export interface NoteBatchResult {
  ok: string[];
  failed: { id: string; error: string }[];
  action: string;
  count: number;
  paths?: string[];
}

export function useBatchNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ ids, action }: { ids: string[]; action: NoteBatchAction }) => {
      return (await batchNotes(ids, action)) as NoteBatchResult;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void invalidateOverviewQueries(qc);
    },
  });
}

export function useRenameNoteTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { old: string; new: string }) => {
      await renameNoteTag(input.old, input.new);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      void qc.invalidateQueries({ queryKey: ['noteTags'] });
    },
  });
}
