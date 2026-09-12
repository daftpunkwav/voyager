/**
 * @file sources.ts
 * @description Resource library domain: repo/doc/web resources plus cross-kind listings.
 *
 * Document upload is a mandatory two-step flow: uploadFile persists the file
 * to disk, then add_document registers it in the library. All functions
 * return payloads directly, without a {data} envelope; docFileUrl is a
 * synchronous pure function.
 *
 * Responsibilities:
 * - Cross-kind library access: list_sources and sources_stats over
 *   repo/doc/web resources
 * - Orchestrate the two-step document upload (disk persist, then register)
 * - Serve document sections and web clippings: save_url, meta updates,
 *   removal, and the original-file download URL
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, unwrapDataField, uploadFile } from '@/bridge/client';

type Payload = Record<string, unknown>;

// ---- Repositories (repo) ----

export function importRepo(url: string, category = ''): Promise<unknown> {
  return callCapability('sources', 'import_repo', { url, category }).then(unwrapDataField);
}

// ---- Cross-kind ----

export function listSources(p?: {
  kind?: string;
  status?: string;
  tag?: string;
  query?: string;
  sort?: string;
  desc?: boolean;
  limit?: number;
}): Promise<unknown> {
  return callCapability('sources', 'list_sources', p ?? {}).then(unwrapDataField);
}

export function sourcesStats(): Promise<Payload> {
  return callCapability('sources', 'sources_stats', {}).then(unwrapDataField<Payload>);
}

// ---- Documents (doc) ----

/** Composite flow: upload to disk, then register via the capability — both steps are mandatory. */
export async function uploadDocument(
  file: File,
  meta: { title?: string; tags?: string[]; category?: string } = {}
): Promise<unknown> {
  const { file_path, filename } = await uploadFile(file);
  return callCapability('sources', 'add_document', {
    file_path,
    title: meta.title || filename,
    tags: meta.tags,
    category: meta.category,
  }).then(unwrapDataField);
}

export function getDocument(docId: string): Promise<Payload> {
  return callCapability('sources', 'get_document', { doc_id: docId }).then(
    unwrapDataField<Payload>
  );
}

export function getDocSection(docId: string, sectionNo: number): Promise<unknown> {
  return callCapability('sources', 'get_doc_section', {
    doc_id: docId,
    section_no: sectionNo,
  }).then(unwrapDataField);
}

export function setDocumentMeta(
  docId: string,
  d: { title?: string; category?: string; tags?: string[]; progress?: string; note?: string }
): Promise<unknown> {
  return callCapability('sources', 'set_document_meta', { doc_id: docId, ...d }).then(
    unwrapDataField
  );
}

export function removeDocument(docId: string): Promise<unknown> {
  return callCapability('sources', 'remove_document', { doc_id: docId }).then(unwrapDataField);
}

/** Download URL for the document's original file (inline preview, e.g. opening PDFs
 *  directly). Synchronous pure function: safe to call from render paths. */
export function docFileUrl(docId: string): string {
  return `/api/sources/files/doc/${docId}`;
}

// ---- Web clippings (web) ----

export function saveUrl(
  url: string,
  meta: { title?: string; tags?: string[]; category?: string } = {}
): Promise<unknown> {
  return callCapability('sources', 'save_url', { url, ...meta }).then(unwrapDataField);
}

export function getPage(pageId: string): Promise<Payload> {
  return callCapability('sources', 'get_page', { page_id: pageId }).then(unwrapDataField<Payload>);
}

export function setPageMeta(
  pageId: string,
  d: { title?: string; tags?: string[]; category?: string }
): Promise<unknown> {
  return callCapability('sources', 'set_page_meta', { page_id: pageId, ...d }).then(
    unwrapDataField
  );
}

export function removePage(pageId: string): Promise<unknown> {
  return callCapability('sources', 'remove_page', { page_id: pageId }).then(unwrapDataField);
}
