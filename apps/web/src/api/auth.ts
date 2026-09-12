/**
 * @file auth.ts
 * @description Auth and GitHub account domain for the local single-user setup.
 *
 * Sessions ride on a gateway cookie; there is no user entity and no OAuth
 * flow: me/account listing are local stubs and GitHub authorization is a
 * token pasted in the settings page (sources.set_github_token). All
 * functions return payloads directly, without a {data} envelope.
 *
 * Responsibilities:
 * - Bind a GitHub access token via sources.set_github_token (secret stays
 *   backend-side; the masked flag comes back)
 * - List starred repos through sources.list_starred_repos
 * - Provide local single-user stubs for account listing and unbinding
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability } from '@/bridge/client';
import type { StarsListResult } from '@/api/types';

/** Local single-user stub: GitHub authorization is token-based, so there are no account entities to list. */
export type GitHubAccountRow = { id: string; username: string; pat_masked: string };

export function listGithubAccounts(): Promise<GitHubAccountRow[]> {
  return Promise.resolve([]);
}

/** GitHub binding: the settings page submits a token via sources.set_github_token (the secret is stored backend-only). */
export function setGithubToken(token: string): Promise<{ has_token: boolean }> {
  return callCapability<{ has_token: boolean }>('sources', 'set_github_token', { token });
}

/** Local single-user stub. */
export function unbindGithub(): Promise<{ success: boolean }> {
  return Promise.resolve({ success: true });
}

/** GitHub stars (real bridge: list_starred_repos; without a token the backend rate-limit error steers users to the settings page). */
export async function listStars(username: string, limit = 100): Promise<StarsListResult> {
  const items = await callCapability<StarsListResult['items']>('sources', 'list_starred_repos', {
    username,
    limit,
  });
  return { items, total: Array.isArray(items) ? items.length : 0 };
}
