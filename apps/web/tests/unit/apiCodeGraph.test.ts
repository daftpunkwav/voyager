/**
 * @file apiCodeGraph
 * @description Pins the L1 code-graph domain contract (api/codeGraph.ts):
 * the status-vocabulary mapping (single mapping point), lifecycle capability
 * names, and the shared RawSubgraph unwrapping.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({
  callCapability: callCapabilityMock,
  unwrapDataField: (r: unknown) =>
    r && typeof r === 'object' && 'data' in (r as object) ? (r as { data: unknown }).data : r,
}));

import {
  listCodeGraphIndexStatuses,
  cancelCodeGraphIndex,
  triggerCodeGraphIndex,
  refreshCodeGraphIndex,
  deleteCodeGraphIndex,
  getCodeGraph,
  batchIndexCodeGraph,
} from '@/api/codeGraph';

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('api/codeGraph status mapping', () => {
  it('maps known statuses (incl. lowercase input) onto the canonical vocabulary', async () => {
    callCapabilityMock.mockResolvedValue([
      { id: 1, project: 'p1', repo_path: '/r/1', status: 'queued' },
      { id: 2, project: 'p2', repo_path: '/r/2', status: 'RUNNING' },
      { id: 3, project: 'p3', repo_path: '/r/3', status: 'DONE' },
      { id: 4, project: 'p4', repo_path: '/r/4', status: 'CANCELLED' },
      { id: 5, project: 'p5', repo_path: '/r/5', status: 'FAILED' },
    ]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items.map((i) => i.status)).toEqual([
      'QUEUED',
      'INDEXING',
      'READY',
      'STALE',
      'INDEX_FAILED',
    ]);
    expect(items[0]).toMatchObject({
      id: '1',
      project_id: 'p1',
      engine_project: '/r/1',
      created_ts: 0,
      updated_ts: 0,
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'list_index_jobs', {});
  });

  it('routes unknown statuses to INDEX_FAILED instead of dropping the row', async () => {
    callCapabilityMock.mockResolvedValue([
      { id: 'x', status: 'MYSTERY', error: 'boom', created_ts: 3, updated_ts: 4 },
    ]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items[0]).toMatchObject({ status: 'INDEX_FAILED', error: 'boom', created_ts: 3 });
  });

  it('tolerates a missing/bare payload and omits error when falsy', async () => {
    callCapabilityMock.mockResolvedValue(null);
    await expect(listCodeGraphIndexStatuses()).resolves.toEqual({ items: [] });
    callCapabilityMock.mockResolvedValue([{ id: 'a', status: 'READY', error: '' }]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items[0].error).toBeUndefined();
  });
});

describe('api/codeGraph lifecycle wrappers', () => {
  it('cancel/drop route by project id and unwrap {data}', async () => {
    callCapabilityMock.mockResolvedValue({ data: 'ok-cancel' });
    await expect(cancelCodeGraphIndex('p1')).resolves.toBe('ok-cancel');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'cancel_index', { project: 'p1' });

    callCapabilityMock.mockResolvedValue({ data: 'ok-drop' });
    await expect(deleteCodeGraphIndex('p2')).resolves.toBe('ok-drop');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'drop_project_graph', {
      project: 'p2',
    });
  });

  it('trigger and refresh share enqueue_index (semantic alias), spreading options', async () => {
    callCapabilityMock.mockResolvedValue({});
    await triggerCodeGraphIndex('p1', { mode: 'full' });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project: 'p1',
      mode: 'full',
    });
    await refreshCodeGraphIndex('p1');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', { project: 'p1' });
  });

  it('batchIndexCodeGraph sends project_ids plus mode', async () => {
    callCapabilityMock.mockResolvedValue({});
    await batchIndexCodeGraph(['a', 'b'], 'fast');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project_ids: ['a', 'b'],
      mode: 'fast',
    });
  });

  it('getCodeGraph unwraps the shared RawSubgraph shape', async () => {
    const subgraph = { nodes: [{}], edges: [{}], stats: { node_count: 1 } };
    callCapabilityMock.mockResolvedValue({ data: subgraph });
    await expect(getCodeGraph('p1', { max_nodes: 10 })).resolves.toEqual(subgraph);
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'get_subgraph', {
      project: 'p1',
      max_nodes: 10,
    });
  });
});
