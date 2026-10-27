/**
 * @file runInstances
 * @description Shared shape of the panel's polled subagent instances and the
 * mapping from an instance onto the resident roster row that owns it.
 *
 * Responsibilities:
 * - Describe a list_subagents.running entry (the run dialog's reference
 *   shape plus the panel's own session filter field)
 * - Resolve which resident teammate (or the generic list) owns a run
 *
 * Constraints:
 * - This module must not depend on UI-layer components at runtime: the run
 *   dialog's reference shape is taken as a type only, so the import is erased
 *   at compile time and carries no component code into this module.
 */

import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { canonicalPersonaId } from '@/constants/personas';
import type { SubagentRunRef } from '@/widgets/chat/SubagentRunDialog';

/** A list_subagents.running entry (status is a RunStatus.value from agent/runtime/state.py).
 *  Extends the run dialog's SubagentRunRef contract instead of re-declaring the
 *  shared fields, so the two shapes cannot drift. */
export interface RunningInstance extends SubagentRunRef {
  /** Chat session this run belongs to ('' = session-less / older backend). */
  session?: string;
}

const RESIDENT_IDS = new Set(AGENT_CATALOG.map((a) => a.id));

/** Which resident roster row owns a run: the main conversational run belongs
 *  to Lucien, a run whose persona maps onto a roster agent lights that
 *  teammate's own row; null = a generic (unnamed) run, listed below the
 *  roster behind a divider. Unknown custom personas are not residents. */
export function residentRunRow(r: RunningInstance): string | null {
  if (r.conversational === true) return 'orchestrator';
  const persona = r.persona ?? '';
  if (!persona) return null;
  const canonical = canonicalPersonaId(persona);
  return RESIDENT_IDS.has(canonical) ? canonical : null;
}
