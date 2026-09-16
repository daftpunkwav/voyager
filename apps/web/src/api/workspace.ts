/**
 * @file workspace.ts
 * @description Workspace endpoints against the gateway: a read-only
 * machine-wide directory picker used to choose a new workspace root, and
 * the hot-switch endpoint that rebuilds the agent around the new root
 * without restarting the service.
 */

interface MaybeError {
  error?: { code: string; message: string };
}

/** Plain GET against the gateway (these endpoints are REST, not capabilities). */
async function callRest<T>(path: string): Promise<T & MaybeError> {
  const resp = await fetch(path);
  if (!resp.ok) {
    throw new Error(`workspace request failed (${resp.status})`);
  }
  return (await resp.json()) as T & MaybeError;
}

export interface WorkspaceEntry {
  name: string;
  type: 'directory' | 'file';
  size?: number;
}

export interface PickResult {
  path: string;
  parent: string | null;
  home: string;
  entries: WorkspaceEntry[];
}

export async function pickDirectory(path = ''): Promise<PickResult & MaybeError> {
  return callRest(`/api/workspace/pick?path=${encodeURIComponent(path)}`);
}

export interface SwitchResult {
  workspace: string;
  previous?: string;
  note?: string;
}

/** Hot-switch the agent workspace: validates, rebuilds the agent around the
 *  new root, persists agent.workspace.dir and rebinds workspace routes.
 *  `marker` (optional request id) is echoed on the workspace.switched event
 *  so the initiating tab can recognize its own broadcast; omitted from the
 *  wire when unset. Caller contract: a surface whose tab subscribes to SSE
 *  (useChatStream is mounted, e.g. via FloatingChat) must generate a marker
 *  and stash it in chatStore.workspaceSwitchMarker BEFORE calling — the
 *  broadcast races the HTTP response, and an unstashed marker means the
 *  initiating tab sees the misleading "switched elsewhere" toast. Throws the
 *  backend message on failure (validation / rebuild errors). */
export async function switchWorkspace(dir: string, marker = ''): Promise<SwitchResult> {
  const resp = await fetch('/api/workspace/switch', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(marker ? { dir, marker } : { dir }),
  });
  const data = (await resp.json().catch(() => ({}))) as SwitchResult & MaybeError;
  if (!resp.ok || data.error) {
    throw new Error(data.error?.message ?? `workspace switch failed (${resp.status})`);
  }
  return data;
}
