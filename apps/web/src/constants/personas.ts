/**
 * @file personas
 * @description Canonical persona duty ids and their legacy aliases. Display
 * names live in AGENT_CATALOG / the backend personas data layer.
 *
 * Responsibilities:
 * - Define the canonical persona duty ids
 * - Canonicalize legacy aliases to duty ids; unknown ids pass through so
 *   custom subagents are never misattributed
 * - Map ids to display names and agent CSS classes
 *
 * This module must not depend on UI-layer components.
 */

export const PERSONA_IDS = [
  'orchestrator',
  'recon',
  'explainer',
  'organizer',
  'graph_guide',
] as const;

export type PersonaDutyId = (typeof PERSONA_IDS)[number];

const ALIASES: Record<string, PersonaDutyId> = {
  orchestrator: 'orchestrator',
  lucien: 'orchestrator',
  hub: 'orchestrator',
  recon: 'recon',
  iris: 'recon',
  scout: 'recon',
  navigator: 'recon',
  explainer: 'explainer',
  elio: 'explainer',
  mentor: 'explainer',
  organizer: 'organizer',
  miyai: 'organizer',
  curator: 'organizer',
  scribe: 'organizer',
  graph_guide: 'graph_guide',
  atlas: 'graph_guide',
};

export function canonicalPersonaId(id: string | null | undefined): string {
  if (!id) return 'orchestrator';
  // Return unknown ids as-is (custom subagents); never collapse them to
  // orchestrator, or SSE speaker switches would be misattributed to Lucien
  return ALIASES[id] ?? id;
}

export function isOrchestrator(id: string | null | undefined): boolean {
  return canonicalPersonaId(id) === 'orchestrator';
}

export function personaCssClass(id: string | null | undefined): string {
  return `agent-${canonicalPersonaId(id)}`;
}

/** Duty id / legacy alias -> display name (data layer). */
export const PERSONA_DISPLAY_NAME: Record<string, string> = {
  orchestrator: 'Lucien',
  hub: 'Lucien',
  lucien: 'Lucien',
  recon: 'Iris',
  scout: 'Iris',
  navigator: 'Iris',
  iris: 'Iris',
  explainer: 'Elio',
  mentor: 'Elio',
  elio: 'Elio',
  organizer: 'Miyai',
  curator: 'Miyai',
  scribe: 'Miyai',
  miyai: 'Miyai',
  graph_guide: 'Atlas',
  atlas: 'Atlas',
};

export function personaDisplayName(id: string | null | undefined): string {
  if (!id) return PERSONA_DISPLAY_NAME.orchestrator;
  return PERSONA_DISPLAY_NAME[id] ?? PERSONA_DISPLAY_NAME[canonicalPersonaId(id)] ?? id;
}
