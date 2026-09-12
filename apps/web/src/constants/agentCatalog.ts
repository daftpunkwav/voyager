/**
 * @file agentCatalog
 * @description Single source of truth for the agent catalog. `id` is the
 * structural role id; `name` is the display name.
 *
 * Display copy (tagline/intro) resolves through the agent namespace via
 * getters so access stays lazy: other domains read these fields directly and
 * runtime language switches re-resolve without a reload.
 *
 * Responsibilities:
 * - Define the structural agent roles: role id, display name, and color
 * - Resolve tagline/intro lazily through agent-namespace getters so
 *   runtime language switches re-resolve without a reload
 * - Carry the carousel timing constants for catalog presentation
 *
 * This module must not depend on UI-layer components.
 */
import { i18n } from '@/i18n';

export interface AgentDefinition {
  id: string;
  name: string;
  /** Short label (left side of the card). */
  tagline: string;
  /** Longer copy (right side of the card in the 0.618:1 layout). */
  intro: string;
  color: string;
}

/** Number of agents fully visible in the viewport. */
export const AGENT_CAROUSEL_VISIBLE = 4;

/** Auto-carousel interval in ms — intentionally slow for readability. */
export const AGENT_CAROUSEL_INTERVAL_MS = 5_000;

/** Slide transition duration in ms. */
export const AGENT_CAROUSEL_TRANSITION_MS = 900;

export const AGENT_CATALOG: AgentDefinition[] = [
  {
    id: 'orchestrator',
    name: 'Lucien',
    get tagline() {
      return i18n.t('agent:catalog.orchestrator.tagline');
    },
    get intro() {
      return i18n.t('agent:catalog.orchestrator.intro');
    },
    color: 'linear-gradient(135deg,#4a3aff,#9d4edd)',
  },
  {
    id: 'recon',
    name: 'Iris',
    get tagline() {
      return i18n.t('agent:catalog.recon.tagline');
    },
    get intro() {
      return i18n.t('agent:catalog.recon.intro');
    },
    color: 'linear-gradient(135deg,#ff9f0a,#ff6f00)',
  },
  {
    id: 'explainer',
    name: 'Elio',
    get tagline() {
      return i18n.t('agent:catalog.explainer.tagline');
    },
    get intro() {
      return i18n.t('agent:catalog.explainer.intro');
    },
    color: 'linear-gradient(135deg,#9d4edd,#c879ff)',
  },
  {
    id: 'organizer',
    name: 'Miyai',
    get tagline() {
      return i18n.t('agent:catalog.organizer.tagline');
    },
    get intro() {
      return i18n.t('agent:catalog.organizer.intro');
    },
    color: 'linear-gradient(135deg,#34c759,#30d158)',
  },
  {
    id: 'graph_guide',
    name: 'Atlas',
    get tagline() {
      return i18n.t('agent:catalog.graph_guide.tagline');
    },
    get intro() {
      return i18n.t('agent:catalog.graph_guide.intro');
    },
    color: 'linear-gradient(135deg,#5ac8fa,#007aff)',
  },
];
