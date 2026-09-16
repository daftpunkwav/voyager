/**
 * @file defsEvents
 * @description Module-level change notifications for custom subagent definitions (no React Context).
 *
 * SpawnForm notifies after a successful spawn; DefinitionGrid subscribes to re-fetch.
 */

type DefsListener = () => void;

const listeners: Set<DefsListener> = new Set();

/** Subscribe to custom definition changes; returns an unsubscribe function. */
export function onTeamDefsChanged(fn: DefsListener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Emit one custom-definition change notification. */
export function notifyTeamDefsChanged(): void {
  listeners.forEach((fn) => fn());
}
