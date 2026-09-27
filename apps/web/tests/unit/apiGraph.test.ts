/**
 * @file apiGraph
 * @description Pins the L0 graph domain contract (api/graph.ts): capability
 * names, argument defaults, and the direct payload passthrough.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({
  callCapability: callCapabilityMock,
}));

import { getGraph, enqueueL0 } from '@/api/graph';

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('api/graph', () => {
  it('getGraph calls graph.l0_view with empty args by default and resolves the payload as-is', async () => {
    callCapabilityMock.mockResolvedValue({ nodes: [] });
    await expect(getGraph()).resolves.toEqual({ nodes: [] });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'l0_view', {});
  });

  it('getGraph forwards kinds and limit', async () => {
    callCapabilityMock.mockResolvedValue({ nodes: [] });
    await getGraph({ kinds: ['repo'], limit: 5 });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'l0_view', {
      kinds: ['repo'],
      limit: 5,
    });
  });

  it('enqueueL0 defaults priority to 100 and resolves the payload as-is', async () => {
    callCapabilityMock.mockResolvedValue({ queued: 1 });
    await expect(enqueueL0(['repo'])).resolves.toEqual({ queued: 1 });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_l0', {
      kinds: ['repo'],
      priority: 100,
    });
  });
});
