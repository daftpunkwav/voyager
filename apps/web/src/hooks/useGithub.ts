/**
 * @file useGithub
 * @description GitHub account/stars hooks (auth domain), kept separate from project CRUD.
 *
 * Responsibilities:
 * - Query starred repos by username (enabled only with a username) and adapt
 *   raw GitHub entries to the StarRepo shape
 * - Expose the local single-user account listing stub
 */

import { useQuery } from '@tanstack/react-query';
import { listGithubAccounts, listStars } from '@/api/auth';

/** Real GitHub stars bridge: list_starred_repos requires a username (this single-user
 *  build has no built-in account, so the drawer asks once and localStorage remembers).
 *  Raw GitHub entries are adapted to the StarRepo shape. */
export function useGithubStars(options?: { username?: string; enabled?: boolean }) {
  const username = options?.username ?? '';
  return useQuery({
    queryKey: ['githubStars', username],
    queryFn: async () => {
      const res = await listStars(username);
      // Backend rows are already normalized (github.list_starred):
      // {owner, name, url, description, stars, language}
      const raw = res.items ?? [];
      const items = raw.map((r) => {
        const owner = r.owner ?? '';
        const repo = r.name ?? '';
        const link = r.url || `https://github.com/${owner}/${repo}`;
        return {
          full_name: `${owner}/${repo}`,
          owner,
          repo,
          description: r.description ?? '',
          stars: r.stars ?? 0,
          language: r.language || null,
          html_url: link,
          url: link,
        };
      });
      return { items, total: items.length, cached: false, fetched_at: Date.now() };
    },
    enabled: (options?.enabled ?? true) && Boolean(username),
    staleTime: 5 * 60 * 1000,
  });
}

export function useGithubAccounts() {
  return useQuery({
    queryKey: ['githubAccounts'],
    queryFn: () => listGithubAccounts(),
  });
}
