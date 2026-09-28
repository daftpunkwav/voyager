/**
 * @file workspaceSwitch.ts
 * @description Shared hot-switch protocol for every surface that switches the
 * agent workspace (the composer chip's browser, the settings WorkspaceBlock).
 *
 * The switch handshake is a two-party protocol over
 * chatStore.workspaceSwitchMarker and lives only here (single implementation
 * on both sides):
 * - The initiator stashes a fresh marker BEFORE the POST fires (see
 *   switchWorkspaceWithMarker): the workspace.switched SSE broadcast races
 *   the HTTP response, and a marker that is not already stashed makes
 *   useChatStream misread this tab's own switch as "switched elsewhere" and
 *   raise a misleading toast.
 * - The SSE reader (hooks/useChatStream) recognizes its own echo through
 *   consumeWorkspaceSwitchMarker, which clears the marker on match.
 *
 * Do not inline either half at call sites, and do not POST
 * api/workspace.switchWorkspace directly from an SSE-subscribed tab.
 */

import { useChatStore } from '@/stores/chatStore';
import { switchWorkspace } from '@/api/workspace';

/** Generate a fresh request id and stash it as this tab's switch marker
 *  (the initiating half of the handshake). Returns the marker for the POST. */
function stashWorkspaceSwitchMarker(): string {
  const marker = crypto.randomUUID();
  useChatStore.setState({ workspaceSwitchMarker: marker });
  return marker;
}

/** Whether a workspace.switched broadcast echoes this tab's own marker (the
 *  recognizing half of the handshake). A match is consumed (cleared), so a
 *  replayed broadcast with the same id cannot match twice. */
export function consumeWorkspaceSwitchMarker(marker: string): boolean {
  if (marker === '' || marker !== useChatStore.getState().workspaceSwitchMarker) return false;
  useChatStore.setState({ workspaceSwitchMarker: null });
  return true;
}

/** Stash a fresh marker, POST the switch, resolve with the new workspace
 *  path. Throws the backend message on failure (validation / rebuild). */
export async function switchWorkspaceWithMarker(next: string): Promise<string> {
  const marker = stashWorkspaceSwitchMarker();
  const res = await switchWorkspace(next, marker);
  return res.workspace;
}
