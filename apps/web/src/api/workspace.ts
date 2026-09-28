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

/** Setting key backing the agent workspace (agent.workspace.dir). Lives here
 *  because the workspace domain owns it: read by the settings WorkspaceBlock
 *  and the composer's workspace chip, switched by switchWorkspace below. */
export const WORKDIR_KEY = 'agent.workspace.dir';

/** Plain GET against the gateway (these endpoints are REST, not capabilities). */
async function callRest<T>(path: string): Promise<T & MaybeError> {
  const resp = await fetch(path);
  if (!resp.ok) {
    throw new Error(`workspace request failed (${resp.status})`);
  }
  // A 200 with a non-JSON body must not surface the browser's raw
  // SyntaxError copy to the user
  const body = (await resp.json().catch(() => null)) as (T & MaybeError) | null;
  if (!body) {
    throw new Error('workspace request failed (invalid response body)');
  }
  return body;
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
 *  wire when unset. SSE-subscribed tabs must not call this directly: the
 *  marker handshake (stash before POST, recognize the echo) lives in
 *  bridge/workspaceSwitch — its switchWorkspaceWithMarker is the only caller
 *  that should pass a marker, because an unstashed marker makes the
 *  initiating tab see the misleading "switched elsewhere" toast. Throws the
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
