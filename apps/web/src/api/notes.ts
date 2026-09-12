/**
 * @file notes.ts
 * @description Notes domain (notes service), with equal rights for user and agent.
 *
 * Capability names mirror the operations they perform. All functions return
 * payloads directly, without a {data} envelope.
 *
 * Responsibilities:
 * - Cover the note lifecycle: CRUD, server-side search, trash restore/purge,
 *   versions, tags, backlinks, TOC, export and batch actions
 * - Carry the notes-view preference snapshot (get/set_notes_view) with
 *   caller-side generics so this layer stays free of page types
 * - Register note assets (attachment files) under notes.add_asset
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';
import type { Note } from '@/api/types';

/** List notes under one resource (backend defines the semantics of an empty source_id). */
export function listNotes(sourceId: string): Promise<Note[]> {
  return callCapability('notes', 'list_notes', { source_id: sourceId }).then(
    unwrapDataField<Note[]>
  );
}

/** All notes (for indexing/migration). */
export function listAllNotes(): Promise<Note[]> {
  return callCapability('notes', 'list_notes', {}).then(unwrapDataField<Note[]>);
}

/** Server-side search via the list_notes query: LIKE match over title + body with hit-window excerpts. */
export function searchNotes(
  query: string,
  extra: { tag?: string; state?: string; sort?: string; limit?: number } = {}
): Promise<unknown> {
  return callCapability('notes', 'list_notes', { query, ...extra }).then(unwrapDataField);
}

export function getNote(id: string): Promise<Note> {
  return callCapability('notes', 'get_note', { note_id: id }).then(unwrapDataField<Note>);
}

/** UI preference snapshot (equal rights for user and agent). Callers narrow the
 *  shape via generics (pages/notes/notesView NotesViewSnapshot); the api layer
 *  does not depend on page types. */
export function getNotesView<T = Record<string, unknown>>(): Promise<T> {
  return callCapability<T>('notes', 'get_notes_view').then(unwrapDataField<T>);
}

export function setNotesView<T = Record<string, unknown>>(d: Record<string, unknown>): Promise<T> {
  return callCapability<T>('notes', 'set_notes_view', d).then(unwrapDataField<T>);
}

export function createNote(
  projectId: string,
  d: { title: string; content: string }
): Promise<Note> {
  return callCapability('notes', 'create_note', {
    source_id: projectId,
    title: d.title,
    content: d.content,
  }).then(unwrapDataField<Note>);
}

export function updateNote(id: string, d: Record<string, unknown>): Promise<unknown> {
  return callCapability('notes', 'update_note', { note_id: id, ...d }).then(unwrapDataField);
}

export function deleteNote(id: string): Promise<unknown> {
  return callCapability('notes', 'delete_note', { note_id: id }).then(unwrapDataField);
}

export function listNoteTags(): Promise<unknown> {
  return callCapability('notes', 'list_tags', {}).then(unwrapDataField);
}

export function getBacklinks(id: string): Promise<unknown> {
  return callCapability('notes', 'get_backlinks', { note_id: id }).then(unwrapDataField);
}

export function getNoteToc(id: string): Promise<unknown> {
  return callCapability('notes', 'get_note_toc', { note_id: id }).then(unwrapDataField);
}

export function restoreNote(id: string): Promise<unknown> {
  return callCapability('notes', 'restore_note', { note_id: id }).then(unwrapDataField);
}

export function purgeNote(id: string): Promise<unknown> {
  return callCapability('notes', 'purge_note', { note_id: id }).then(unwrapDataField);
}

export function emptyTrash(): Promise<unknown> {
  return callCapability('notes', 'empty_trash', {}).then(unwrapDataField);
}

export function listVersions(id: string): Promise<unknown> {
  return callCapability('notes', 'list_versions', { note_id: id }).then(unwrapDataField);
}

export function restoreVersion(id: string, version: number): Promise<unknown> {
  return callCapability('notes', 'restore_version', { note_id: id, version }).then(unwrapDataField);
}

export function renameNoteTag(oldName: string, newName: string): Promise<unknown> {
  return callCapability('notes', 'rename_tag', { old: oldName, new: newName }).then(
    unwrapDataField
  );
}

export function linkNote(id: string, sourceId: string | null): Promise<unknown> {
  return callCapability('notes', 'link_note', { note_id: id, source_id: sourceId }).then(
    unwrapDataField
  );
}

export function exportNote(id: string): Promise<unknown> {
  return callCapability('notes', 'export_note', { note_id: id }).then(unwrapDataField);
}

export function batchNotes(ids: string[], action: string): Promise<unknown> {
  return callCapability('notes', 'batch_notes', { ids, action }).then(unwrapDataField);
}

export function addAsset(filePath: string, filename = '', noteId = ''): Promise<unknown> {
  return callCapability('notes', 'add_asset', {
    file_path: filePath,
    filename,
    note_id: noteId,
  }).then(unwrapDataField);
}
