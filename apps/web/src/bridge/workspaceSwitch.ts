/**
 * @file workspaceSwitch.ts
 * @description Shared hot-switch protocol for every surface that switches the
 * agent workspace (the composer chip's browser, the settings WorkspaceBlock).
 *
 * The marker MUST be stashed in chatStore before the POST fires: the
 * workspace.switched SSE broadcast races the HTTP response, and a marker that
 * is not already stashed makes useChatStream misread this tab's own switch as
 * "switched elsewhere" and raise a misleading toast. This module is the single
 * implementation of that contract — do not inline the sequence at call sites.
 */

import { useChatStore } from '@/stores/chatStore';
import { switchWorkspace } from '@/api/workspace';

/** Stash a fresh marker, POST the switch, resolve with the new workspace
 *  path. Throws the backend message on failure (validation / rebuild). */
export async function switchWorkspaceWithMarker(next: string): Promise<string> {
  const marker = crypto.randomUUID();
  useChatStore.setState({ workspaceSwitchMarker: marker });
  const res = await switchWorkspace(next, marker);
  return res.workspace;
}
