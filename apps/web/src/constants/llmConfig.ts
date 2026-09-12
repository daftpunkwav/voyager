/**
 * @file llmConfig
 * @description LLM-related option lists and helpers shared by settings UI,
 * kept aligned with the backend LLM provider catalog.
 *
 * `value` fields are API/backend contract values and stay untranslated;
 * display copy lives behind settings:* i18n keys (labelKey / descKey).
 *
 * Responsibilities:
 * - List API-format and speaking-style options: untranslated contract
 *   values paired with settings-namespace label keys
 * - Build default per-agent LLM configs from the agent catalog
 * - Resolve speaking styles to localized labels, unknown values as-is
 *
 * This module must not depend on UI-layer components.
 */

import type { AgentLlmConfig, AgentSpeakingStyle, LlmApiFormat } from '@/api/types';
import { i18n } from '@/i18n';
import { AGENT_CATALOG } from '@/constants/agentCatalog';

/** API format options (aligned with the backend LLM catalog: chat / anthropic only) */
export const LLM_API_FORMAT_OPTIONS: { value: LlmApiFormat; labelKey: string; hint: string }[] = [
  { value: 'chat', labelKey: 'settings:llm.format.chat', hint: '/v1/chat/completions' },
  { value: 'anthropic', labelKey: 'settings:llm.format.anthropic', hint: '/v1/messages' },
];

/** Agent speaking styles */
export const SPEAKING_STYLE_OPTIONS: {
  value: AgentSpeakingStyle;
  labelKey: string;
  descKey: string;
}[] = [
  {
    value: 'default',
    labelKey: 'settings:llm.style.default',
    descKey: 'settings:llm.style.defaultDesc',
  },
  { value: 'warm', labelKey: 'settings:llm.style.warm', descKey: 'settings:llm.style.warmDesc' },
  { value: 'sharp', labelKey: 'settings:llm.style.sharp', descKey: 'settings:llm.style.sharpDesc' },
  {
    value: 'professional',
    labelKey: 'settings:llm.style.professional',
    descKey: 'settings:llm.style.professionalDesc',
  },
  {
    value: 'humorous',
    labelKey: 'settings:llm.style.humorous',
    descKey: 'settings:llm.style.humorousDesc',
  },
  {
    value: 'concise',
    labelKey: 'settings:llm.style.concise',
    descKey: 'settings:llm.style.conciseDesc',
  },
  {
    value: 'mentor',
    labelKey: 'settings:llm.style.mentor',
    descKey: 'settings:llm.style.mentorDesc',
  },
  {
    value: 'socratic',
    labelKey: 'settings:llm.style.socratic',
    descKey: 'settings:llm.style.socraticDesc',
  },
];

/** Build default LLM configs for every agent in the catalog. */
export function createDefaultAgentLlmConfigs(): AgentLlmConfig[] {
  return AGENT_CATALOG.map((a) => ({
    agent_id: a.id,
    provider_id: null,
    model_override: null,
    speaking_style: 'default' as AgentSpeakingStyle,
  }));
}

/** Resolve a speaking style to its display label; unknown styles render as-is. */
export function speakingStyleLabel(style: AgentSpeakingStyle): string {
  const opt = SPEAKING_STYLE_OPTIONS.find((o) => o.value === style);
  return opt ? i18n.t(opt.labelKey) : style;
}
