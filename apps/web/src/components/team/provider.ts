/**
 * @file provider
 * @description Team-page awareness: count snapshot of personas, custom subagents, and running instances.
 *
 * Each section patches its field after a successful mount. The snapshot is only
 * reported once all three fields have arrived, so a failed load never surfaces
 * as a misleading 0 — the overall snapshot stays null until then.
 *
 * Responsibilities:
 * - Hold the per-field patch state and commit the snapshot only when all
 *   three counts have arrived
 * - Report the localized persona/definition/running count line; null
 *   until the snapshot is complete
 * - Support full-snapshot overwrite and clear (tests, forced resets)
 */

import { i18n } from '@/i18n';
import type { PageProbe } from '@/bridge/pageContext';

export interface TeamSnapshot {
  personas: number;
  definitions: number;
  running: number;
}

/** Whether each field has been patched at least once; reported only when all three have arrived. */
interface PatchState {
  personas?: number;
  definitions?: number;
  running?: number;
}

const patched: PatchState = {};
let snapshot: TeamSnapshot | null = null;

function maybeCommit(): void {
  if (
    typeof patched.personas === 'number' &&
    typeof patched.definitions === 'number' &&
    typeof patched.running === 'number'
  ) {
    snapshot = {
      personas: patched.personas,
      definitions: patched.definitions,
      running: patched.running,
    };
  }
}

/** Patch fields individually; commits the full snapshot once all three have arrived. */
export function patchTeamSnapshot(next: Partial<TeamSnapshot>): void {
  if (typeof next.personas === 'number') patched.personas = next.personas;
  if (typeof next.definitions === 'number') patched.definitions = next.definitions;
  if (typeof next.running === 'number') patched.running = next.running;
  maybeCommit();
}

/** Overwrite the full snapshot directly (for tests or forced overrides).
 *  Passing null also clears per-field progress so a later single-field patch cannot commit from stale values. */
export function rememberTeamSnapshot(next: TeamSnapshot | null): void {
  if (next === null) {
    snapshot = null;
    delete patched.personas;
    delete patched.definitions;
    delete patched.running;
    return;
  }
  patched.personas = next.personas;
  patched.definitions = next.definitions;
  patched.running = next.running;
  snapshot = { ...next };
}

export function lastTeamSnapshot(): TeamSnapshot | null {
  return snapshot;
}

export const teamProvider: PageProbe = {
  page: 'team',
  report() {
    const s = snapshot;
    if (!s) return null;
    return {
      summary: i18n.t('team:provider.summary', {
        personas: s.personas,
        definitions: s.definitions,
        running: s.running,
      }),
      counts: { personas: s.personas, definitions: s.definitions, running: s.running },
    };
  },
};
