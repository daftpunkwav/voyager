/**
 * @file useSources
 * @description Data hooks for the unified source library: list_sources, documents,
 * web clippings and their combined stream.
 *
 * Event-driven refresh: subscribes to source.added / source.ready /
 * source.removed / task.progress and invalidates the affected queries, so
 * import/parse progress needs no manual refresh.
 *
 * Responsibilities:
 * - Query the unified source stream and stats, document details/sections,
 *   and web clippings
 * - Refresh the affected queries from source.* and task.* SSE events
 *   instead of polling
 * - Wrap meta updates and removals with stream and detail invalidation
 */

import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listSources,
  sourcesStats,
  getDocument,
  getDocSection,
  setDocumentMeta,
  removeDocument,
  saveUrl,
  getPage,
  setPageMeta,
  removePage,
} from '@/api/sources';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';

/** Unified source summary (list_sources response; same shape across kinds, `kind` marked by the backend). */
export interface SourceSummary {
  id: string;
  kind: 'repo' | 'doc' | 'web';
  title: string;
  subtitle: string;
  status: 'importing' | 'parsing' | 'ready' | 'stored' | 'failed' | string;
  progress: string;
  tags: string[];
  category: string;
  added_ts: number;
  updated_ts: number;
  match?: { section_no: number; snippet: string };
}

export interface SourceStats {
  repo: number;
  doc: number;
  web: number;
  importing: number;
  failed: number;
}

const SOURCES_KEYS = ['sourcesStream', 'sourcesStats', 'documents', 'webpages'] as const;

export function useSourceStream(
  params: {
    kind?: string;
    query?: string;
    status?: string;
  } = {}
) {
  return useQuery({
    queryKey: ['sourcesStream', params.kind ?? '', params.query ?? '', params.status ?? ''],
    queryFn: async () => {
      return ((await listSources(params)) ?? []) as SourceSummary[];
    },
  });
}

export function useSourcesStats() {
  return useQuery({
    queryKey: ['sourcesStats'],
    queryFn: async () => (await sourcesStats()) as unknown as SourceStats,
  });
}

/** Refresh the source stream on source.* events (import/parse progress is live; no polling). */
export function useSourceEvents() {
  const qc = useQueryClient();
  useEffect(() => {
    const off = subscribe(
      [
        EventType.SOURCE_ADDED,
        EventType.SOURCE_READY,
        EventType.SOURCE_REMOVED,
        EventType.TASK_FAILED,
      ],
      () => {
        for (const key of SOURCES_KEYS) {
          void qc.invalidateQueries({ queryKey: [key] });
        }
      }
    );
    return off;
  }, [qc]);
}

// ---------- Documents ----------

export interface DocumentDetail {
  id: string;
  title: string;
  filename: string;
  ext: string;
  status: string;
  error: string;
  category: string;
  tags: string[];
  progress: string;
  note: string;
  local_path: string;
  sections: { section_no: number; title: string; page_start: number; page_end: number }[];
  total_sections: number;
}

export function useDocument(docId: string | undefined) {
  return useQuery({
    queryKey: ['documents', docId],
    queryFn: async () => {
      if (!docId) throw new Error('missing doc id');
      return (await getDocument(docId)) as unknown as DocumentDetail;
    },
    enabled: Boolean(docId),
  });
}

/** Parse-progress events: refresh the detail while a document is parsing or on task.failed (status/error update live). */
export function useDocumentEvents(docId: string | undefined) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!docId) return;
    const off = subscribe(
      [EventType.TASK_PROGRESS, EventType.TASK_FAILED, EventType.SOURCE_READY],
      (e) => {
        if (e.payload.source_id === docId) {
          void qc.invalidateQueries({ queryKey: ['documents', docId] });
        }
      }
    );
    return off;
  }, [qc, docId]);
}

export function useDocSection(docId: string | undefined, sectionNo: number | undefined) {
  return useQuery({
    queryKey: ['docSection', docId, sectionNo],
    queryFn: async () => {
      if (!docId || !sectionNo) throw new Error('missing doc id or section no');
      return (await getDocSection(docId, sectionNo)) as {
        section_no: number;
        title: string;
        page_start: number;
        page_end: number;
        text: string;
        total_sections: number;
      };
    },
    enabled: Boolean(docId) && Boolean(sectionNo),
  });
}

export function useRemoveDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (docId: string) => {
      await removeDocument(docId);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useSetDocumentMeta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      docId: string;
      meta: {
        title?: string;
        category?: string;
        tags?: string[];
        progress?: string;
        note?: string;
      };
    }) => {
      await setDocumentMeta(input.docId, input.meta);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['documents'] });
      void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    },
  });
}

// ---------- Web clippings ----------

export interface WebPage {
  id: string;
  title: string;
  url: string;
  domain: string;
  summary: string;
  content: string;
  tags: string[];
  meta: { images?: string[]; chars?: number };
}

export function useWebPage(pageId: string | undefined) {
  return useQuery({
    queryKey: ['webpages', pageId],
    queryFn: async () => {
      if (!pageId) throw new Error('missing page id');
      return (await getPage(pageId)) as unknown as WebPage;
    },
    enabled: Boolean(pageId),
  });
}

export function useSaveUrl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { url: string; title?: string; tags?: string[] }) => {
      await saveUrl(input.url, input);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useRemovePage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (pageId: string) => {
      await removePage(pageId);
    },
    onSuccess: () => {
      for (const key of SOURCES_KEYS) {
        void qc.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useSetPageMeta() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      pageId: string;
      meta: { title?: string; tags?: string[]; category?: string };
    }) => {
      await setPageMeta(input.pageId, input.meta);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['webpages'] });
      void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    },
  });
}
