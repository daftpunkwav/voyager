/**
 * @file sseTextDelta
 * @description Type-narrowing helper for SSE text-delta event payloads (plain
 * cast, no runtime normalization).
 */

import type { SSETextDelta } from '@/api/types';

export function asSSETextDelta(data: Record<string, unknown>): SSETextDelta {
  return data as unknown as SSETextDelta;
}
