/**
 * @file llmConfig
 * @description LLM-related option lists shared by settings UI, kept aligned
 * with the backend LLM provider catalog.
 *
 * `value` fields are API/backend contract values and stay untranslated;
 * display copy lives behind settings:* i18n keys (labelKey).
 *
 * This module must not depend on UI-layer components.
 */

import type { LlmApiFormat } from '@/api/types';

/** API format options (aligned with the backend LLM catalog: chat / anthropic / responses) */
export const LLM_API_FORMAT_OPTIONS: { value: LlmApiFormat; labelKey: string; hint: string }[] = [
  { value: 'chat', labelKey: 'settings:llm.format.chat', hint: '/v1/chat/completions' },
  { value: 'anthropic', labelKey: 'settings:llm.format.anthropic', hint: '/v1/messages' },
  { value: 'responses', labelKey: 'settings:llm.format.responses', hint: '/v1/responses' },
];
