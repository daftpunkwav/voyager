/**
 * @file apiCodeGraph
 * @description Pins the L1 code-graph domain contract (api/codeGraph.ts):
 * the status-vocabulary mapping (single mapping point), lifecycle capability
 * calls against the frozen graph signatures (cancel_index by job_id,
 * enqueue_index with repo_path resolved from the sources repo row), the
 * query_graph read path with src/dst -> source/target edge normalization,
 * and the per-project batch fan-out.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({
  callCapability: callCapabilityMock,
}));

vi.mock('@/api/projects', () => ({
  getProject: (repoId: string) =>
    callCapabilityMock('sources', 'get_repo', { repo_id: repoId }),
}));

vi.mock('@/i18n', () => ({
  i18n: { t: (key: string) => key },
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
      { id: 1, project: 'p1', repo_path: '/r/1', status: 'queued', level: 'l1' },
      { id: 2, project: 'p2', repo_path: '/r/2', status: 'RUNNING', level: 'l1' },
      { id: 3, project: 'p3', repo_path: '/r/3', status: 'DONE', level: 'l1' },
      { id: 4, project: 'p4', repo_path: '/r/4', status: 'CANCELLED', level: 'l1' },
      { id: 5, project: 'p5', repo_path: '/r/5', status: 'FAILED', level: 'l1' },
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

  it('excludes L0 relation jobs (level=l0) from the L1 repo-index facade', async () => {
    callCapabilityMock.mockResolvedValue([
      { id: 'u', project: 'universe', repo_path: '', status: 'DONE', level: 'l0' },
      { id: 'r', project: 'p1', repo_path: '/r/1', status: 'DONE', level: 'l1' },
    ]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items.map((i) => i.id)).toEqual(['r']);
  });

  it('routes unknown statuses to INDEX_FAILED instead of dropping the row', async () => {
    callCapabilityMock.mockResolvedValue([
      { id: 'x', status: 'MYSTERY', error: 'boom', created_ts: 3, updated_ts: 4, level: 'l1' },
    ]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items[0]).toMatchObject({ status: 'INDEX_FAILED', error: 'boom', created_ts: 3 });
  });

  it('tolerates a missing/bare payload and omits error when falsy', async () => {
    callCapabilityMock.mockResolvedValue(null);
    await expect(listCodeGraphIndexStatuses()).resolves.toEqual({ items: [] });
    callCapabilityMock.mockResolvedValue([{ id: 'a', status: 'READY', error: '', level: 'l1' }]);
    const { items } = await listCodeGraphIndexStatuses();
    expect(items[0].error).toBeUndefined();
  });
});

describe('api/codeGraph lifecycle wrappers', () => {
  it('cancel routes by queue job_id; drop routes by project', async () => {
    callCapabilityMock.mockResolvedValue('ok-cancel');
    await expect(cancelCodeGraphIndex('job1')).resolves.toBe('ok-cancel');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'cancel_index', { job_id: 'job1' });

    callCapabilityMock.mockResolvedValue('ok-drop');
    await expect(deleteCodeGraphIndex('p2')).resolves.toBe('ok-drop');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'drop_project_graph', {
      project: 'p2',
    });
  });

  it('trigger and refresh share enqueue_index, resolving repo_path from the repo row', async () => {
    callCapabilityMock.mockImplementation((_domain: string, name: string) => {
      if (name === 'get_repo') {
        return Promise.resolve({ id: 'p1', local_path: '/workspace/repo/p1' });
      }
      return Promise.resolve({});
    });
    await triggerCodeGraphIndex('p1');
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project: 'p1',
      repo_path: '/workspace/repo/p1',
    });
    await refreshCodeGraphIndex('p1', { priority: 5 });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project: 'p1',
      repo_path: '/workspace/repo/p1',
      priority: 5,
    });
  });

  it('trigger refuses a repo row without a local clone', async () => {
    callCapabilityMock.mockImplementation((_domain: string, name: string) => {
      if (name === 'get_repo') return Promise.resolve({ id: 'p1', local_path: '' });
      return Promise.resolve({});
    });
    await expect(triggerCodeGraphIndex('p1')).rejects.toThrow('errors:graph.noLocalClone');
    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'graph',
      'enqueue_index',
      expect.anything()
    );
  });

  it('batchIndexCodeGraph enqueues per project and collects failures', async () => {
    callCapabilityMock.mockImplementation((_domain: string, name: string, args: object) => {
      if (name === 'get_repo') {
        const rid = (args as { repo_id: string }).repo_id;
        return Promise.resolve({
          id: rid,
          local_path: rid === 'bad' ? '' : `/workspace/repo/${rid}`,
        });
      }
      return Promise.resolve({});
    });
    await expect(batchIndexCodeGraph(['a', 'bad', 'b'])).resolves.toEqual({
      queued: ['a', 'b'],
      failed: ['bad'],
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project: 'a',
      repo_path: '/workspace/repo/a',
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'enqueue_index', {
      project: 'b',
      repo_path: '/workspace/repo/b',
    });
  });

  it('getCodeGraph queries the project graph and normalizes store edges to source/target', async () => {
    callCapabilityMock.mockResolvedValue({
      project: 'p1',
      nodes: [{ id: 'n1', label: 'File', name: 'a.py', attrs: { status: 'entry' } }],
      edges: [{ id: 'e1', src: 'n1', dst: 'n2', type: 'CALLS' }],
    });
    const res = await getCodeGraph('p1', { limit: 500 });
    expect(callCapabilityMock).toHaveBeenCalledWith('graph', 'query_graph', {
      project: 'p1',
      limit: 500,
    });
    expect(res.edges[0]).toMatchObject({ source: 'n1', target: 'n2', src: 'n1', dst: 'n2' });
    // attrs JSON is merged so renderers read engine fields top-level
    expect(res.nodes[0]).toMatchObject({ id: 'n1', status: 'entry' });
  });
});
