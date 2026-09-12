/**
 * @file types/notes.ts
 * @description Notes domain types (Note / NoteCreate / NoteUpdate).
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

export interface Note {
  id: string;
  title: string;
  content: string;
  excerpt?: string;
  source_id: string;
  project_id?: string;
  node_id?: string;
  tags: string[];
  pinned?: boolean;
  archived?: boolean;
  created_ts: number;
  updated_ts: number;
  created_at?: number;
  /** ISO string form; consumers (NoteList, OverviewPage, ProjectDetailPage) pass it
   *  to helpers like formatRelativeTime / formatDate that expect iso:string. */
  updated_at?: string;
}

export interface NoteCreate {
  title: string;
  content: string;
  source_id?: string;
  project_id?: string;
  tags?: string[];
}

export type NoteUpdate = Partial<NoteCreate>;
