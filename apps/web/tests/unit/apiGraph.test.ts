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

import { getGraph, enqueueL0, getGraphData, toGraphData } from '@/api/graph';

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

  it('getGraphData maps L0 rows: RELATED weight from shared tags, cross edges pinned at 1', async () => {
    expect(
      toGraphData({
        nodes: [
          {
            id: 'repo:1',
            label: '',
            name: 'voyager',
            qualified_name: 'repo:1',
            attrs: { kind: 'repo', tags: ['t'], subtitle: 'desc' },
          },
        ],
        edges: [{ src: 'a', dst: 'b', type: 'RELATED', attrs: { shared_tags: ['x', 'y'] } }],
        cross_edges: [{ src: 'a', dst: 'c', type: 'CROSS_REPO', attrs: {} }],
      })
    ).toEqual({
      nodes: [
        {
          id: 'repo:1',
          name: 'voyager',
          stars: 0,
          kind: 'repo',
          tags: ['t'],
          category: '',
          status: '',
          description: 'desc',
          resourceId: '1',
        },
      ],
      edges: [
        { source: 'a', target: 'b', similarity: 2 / 3, edge_type: 'related' },
        { source: 'a', target: 'c', similarity: 1, edge_type: 'cross_repo' },
      ],
    });
  });

  it('getGraphData forwards args and degrades a missing payload to the empty view', async () => {
    callCapabilityMock.mockResolvedValue(null);
    await expect(getGraphData({ kinds: ['doc'], limit: 5 })).resolves.toEqual({
      nodes: [],
      edges: [],
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'l0_view', {
      kinds: ['doc'],
      limit: 5,
    });
  });
});
