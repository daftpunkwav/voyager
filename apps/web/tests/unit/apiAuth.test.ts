/**
 * @file apiAuth
 * @description Pins the auth/GitHub domain contract (api/auth.ts): local
 * single-user stubs resolve locally, token binding and stars ride the
 * sources capability bridge, and listStars derives total from the payload.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({
  callCapability: callCapabilityMock,
}));

import { listGithubAccounts, setGithubToken, unbindGithub, listStars } from '@/api/auth';

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('api/auth', () => {
  it('listGithubAccounts is a local stub (no bridge call)', async () => {
    await expect(listGithubAccounts()).resolves.toEqual([]);
    expect(callCapabilityMock).not.toHaveBeenCalled();
  });

  it('setGithubToken binds the token through sources.set_github_token', async () => {
    callCapabilityMock.mockResolvedValue({ has_token: true });
    await expect(setGithubToken('ghp_secret')).resolves.toEqual({ has_token: true });
    expect(callCapabilityMock).toHaveBeenCalledWith('sources', 'set_github_token', {
      token: 'ghp_secret',
    });
  });

  it('unbindGithub is a local stub', async () => {
    await expect(unbindGithub()).resolves.toEqual({ success: true });
    expect(callCapabilityMock).not.toHaveBeenCalled();
  });

  it('listStars passes username and limit, deriving total from the items array', async () => {
    const items = [{ full_name: 'a/b' }];
    callCapabilityMock.mockResolvedValue(items);
    await expect(listStars('octocat', 42)).resolves.toEqual({ items, total: 1 });
    expect(callCapabilityMock).toHaveBeenCalledWith('sources', 'list_starred_repos', {
      username: 'octocat',
      limit: 42,
    });
  });

  it('listStars defaults the limit to 100 and tolerates a non-array payload', async () => {
    callCapabilityMock.mockResolvedValue(null);
    await expect(listStars('octocat')).resolves.toEqual({ items: null, total: 0 });
    expect(callCapabilityMock).toHaveBeenCalledWith('sources', 'list_starred_repos', {
      username: 'octocat',
      limit: 100,
    });
  });
});
