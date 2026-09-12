/**
 * @file useLlmAvailable
 * @description LLM availability probe. Uses llm.list_providers to check for a
 * provider with enabled && has_api_key — the same truth as the settings page
 * (!anyUsable) and the backend ServiceLLM; the legacy settings-blob
 * llm_configured flag is not read.
 *
 * Only 'missing' (confirmed no usable key) lets callers show the empty state
 * and disable sending. 'checking'/'unknown' (probe failure, e.g. a flaky
 * network) never lock the chat: sending stays available and the backend
 * ServiceLLM fallback handles it, avoiding false chat lockouts on network jitter.
 *
 * Responsibilities:
 * - Probe llm.list_providers once on mount for enabled && has_api_key
 * - Report a four-state availability; only 'missing' may lock the UI
 */

import { useEffect, useState } from 'react';
import { listProviders } from '@/api/llm';
import type { LlmProvider } from '@/api/types';

export type LlmAvailability = 'checking' | 'ok' | 'missing' | 'unknown';

export function useLlmAvailable(): LlmAvailability {
  const [state, setState] = useState<LlmAvailability>('checking');

  useEffect(() => {
    let alive = true;
    listProviders()
      .then((list: LlmProvider[]) => {
        if (!alive) return;
        const usable = Array.isArray(list) && list.some((p) => p.enabled && p.has_api_key);
        setState(usable ? 'ok' : 'missing');
      })
      .catch(() => {
        if (alive) setState('unknown');
      });
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
