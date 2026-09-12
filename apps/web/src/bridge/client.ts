/**
 * @file client.ts
 * @description Unified capability-call channel: POST /api/<domain>/capabilities/<name>
 * with a single {result}/{error} envelope unwrapping.
 *
 * Also hosts the file-upload transport, the sendBeacon fallback for unload-time
 * saves, and unwrapDataField for legacy {data} envelopes during migration.
 *
 * Responsibilities:
 * - POST capabilities to /api/<domain>/capabilities/<name> with credentials
 *   and trace ids
 * - Unwrap the {result} success envelope and raise ServiceError from {error}
 *   envelopes, including envelope-less proxy failures
 * - Provide the file-upload transport and the sendBeacon unload fallback
 * - Pass legacy top-level {data} envelopes through during migration
 *
 * This module must not depend on UI-layer components.
 */

import { backendUnreachable } from '@/utils/errors';
import { i18n } from '@/i18n';

export class ServiceError extends Error {
  constructor(
    public code: string,
    message: string,
    public hint = '',
    public traceId = '',
    public status = 0
  ) {
    super(message);
    this.name = 'ServiceError';
  }
}

export async function callCapability<T = unknown>(
  domain: string,
  name: string,
  args: Record<string, unknown> = {}
): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api/${domain}/capabilities/${name}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Trace-Id': crypto.randomUUID(),
      },
      body: JSON.stringify(args),
    });
  } catch {
    throw new ServiceError('NETWORK', backendUnreachable());
  }

  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    // Failure responses without a JSON envelope (e.g. the dev/preview proxy
    // returning a 500 with an empty body while the backend is down) are
    // equivalent to "backend unreachable" for users — never shown as a vague
    // "request failed (500)"
    if (body === null) {
      throw new ServiceError('NETWORK', backendUnreachable(), '', '', resp.status);
    }
    const err = body?.error ?? {};
    throw new ServiceError(
      err.code ?? 'UNKNOWN',
      err.message ?? i18n.t('errors:client.requestFailed', { status: resp.status }),
      err.hint ?? '',
      err.trace_id ?? '',
      resp.status
    );
  }
  // The success envelope is always {result: ...}; the 'result' in check (not
  // truthiness) matters: result may legitimately be null/0/false/"" and must
  // not fall through to returning the whole envelope
  if (body && typeof body === 'object' && 'result' in body) return body.result as T;
  return body as T;
}

/** Migration-era equivalent accessor for the legacy API facade: if the result carries a
 *  top-level data key, pass that value through; otherwise return the result as-is.
 *  Can be retired per-domain once every capability is verified to have no data key. */
export function unwrapDataField<T>(result: unknown): T {
  if (result && typeof result === 'object' && 'data' in (result as object)) {
    return (result as { data: T }).data;
  }
  return result as T;
}

/** Browser file upload (a transport action, not a capability): stores under
 *  workspace/imports/ and returns the server-side path. Business validation
 *  (type/size limits) is enforced by the consuming domain capability
 *  (add_document / add_asset). */
export async function uploadFile(
  file: File
): Promise<{ file_path: string; filename: string; size: number }> {
  const form = new FormData();
  form.append('file', file);
  let resp: Response;
  try {
    resp = await fetch('/api/uploads', {
      method: 'POST',
      credentials: 'include',
      body: form,
      headers: { 'X-Trace-Id': crypto.randomUUID() },
    });
  } catch {
    throw new ServiceError('NETWORK', backendUnreachable());
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = body?.error ?? {};
    throw new ServiceError(
      err.code ?? 'UNKNOWN',
      err.message ?? i18n.t('errors:client.uploadFailed', { status: resp.status }),
      err.hint ?? '',
      err.trace_id ?? '',
      resp.status
    );
  }
  return body as { file_path: string; filename: string; size: number };
}

/** Unload fallback channel: fires a capability call via sendBeacon (page-close
 *  scenarios; no response can be awaited, failures are silent). Only for
 *  last-line saves (e.g. the note editor's beforeunload); the normal path is
 *  callCapability. */
export function beaconCapability(domain: string, name: string, body: string): void {
  try {
    navigator.sendBeacon(
      `/api/${domain}/capabilities/${name}`,
      new Blob([body], { type: 'application/json' })
    );
  } catch {
    // A failing beacon cannot be recovered (the page is unloading); stay silent
  }
}
