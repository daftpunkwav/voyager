/**
 * @file stubConfirm
 * @description Test helper for the global confirm dialog: overrides the
 * uiStore.confirm action so tests can answer the imperative confirmDialog()
 * programmatically (window.confirm is no longer used anywhere). Returns the
 * mock for call assertions; the real action is restored after all tests.
 */

import { afterAll, beforeEach, vi } from 'vitest';
import { useUIStore } from '@/stores/uiStore';

export function stubConfirm(answer = true) {
  const original = useUIStore.getState().confirm;
  const confirmMock = vi.fn(async () => answer);
  beforeEach(() => {
    confirmMock.mockClear();
    confirmMock.mockResolvedValue(answer);
    useUIStore.setState({ confirm: confirmMock as unknown as typeof original });
  });
  afterAll(() => {
    useUIStore.setState({ confirm: original });
  });
  return confirmMock;
}
