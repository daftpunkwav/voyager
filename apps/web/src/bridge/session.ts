/**
 * @file session.ts
 * @description Local session bootstrap: writes the session Cookie via a loopback
 * call; subsequent API requests send credentials.
 */

import { backendUnreachable } from '@/utils/errors';

export async function ensureSession(): Promise<void> {
  try {
    await fetch('/api/session/bootstrap', { credentials: 'include' });
  } catch {
    // Don't block the UI when the backend isn't running; later callCapability calls surface NETWORK errors
  }
}

/** Basic liveness probe: GET /health (shared by the health page polling and shell service badges); non-2xx throws with the backend envelope message. */
export async function fetchHealth(signal?: AbortSignal): Promise<unknown> {
  const resp = await fetch('/health', { credentials: 'include', signal });
  if (!resp.ok) {
    const body = (await resp.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? backendUnreachable());
  }
  return resp.json();
}
