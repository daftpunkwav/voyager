/**
 * @file pageProbes.ts
 * @description Page-awareness registry: route -> that page's public provider summary outlet.
 *
 * Each page implements the PageProbe protocol in its own pages/<domain>/
 * provider.ts (report() emits an index row + summary, never body content;
 * returns null while data is not ready and PageProbe skips that report).
 * This table lives in the shell layer: the shell orchestrates pages, so the
 * shell -> pages dependency is legitimate; the widgets/PageProbe component
 * only consumes this table and must never import pages in reverse.
 *
 * Responsibilities:
 * - Register each page's probe under its page name
 * - Resolve a route to its page and probe by prefix matching
 */

import type { PageProbe } from '@/bridge/pageContext';
import { activityProvider } from '@/pages/activity/provider';
import { chatProvider } from '@/pages/chat/provider';
import { graphProvider } from '@/pages/graph/provider';
import { codeGraphProvider } from '@/pages/code-graph/provider';
import { notesProvider } from '@/pages/notes/provider';
import { sourcesProvider, sourceDetailProvider } from '@/pages/sources/provider';
import { teamProvider } from '@/pages/team/provider';

export type { PageProbe } from '@/bridge/pageContext';

/** page name -> probe (each page registers here; page autonomy means a new page is one entry).
 *  code-graph is the graph page's detail view and source-detail the sources detail page;
 *  their probe.page still reports graph / sources respectively (same backend domain). */
export const PAGE_PROBES: Record<string, PageProbe> = {
  chat: chatProvider,
  notes: notesProvider,
  sources: sourcesProvider,
  'source-detail': sourceDetailProvider,
  graph: graphProvider,
  'code-graph': codeGraphProvider,
  team: teamProvider,
  activity: activityProvider,
};

/** Route -> page name (prefix resolution, not an
 *  exact-match dictionary). settings / usage / health / overview intentionally return null:
 *  settings can contain secrets and the overview weekly report is a placeholder dead link. */
export function resolvePageName(pathname: string): string | null {
  if (pathname === '/' || pathname === '/chat' || pathname.startsWith('/chat/')) return 'chat';
  if (pathname === '/notes' || pathname.startsWith('/notes/')) return 'notes';
  if (pathname === '/sources') return 'sources';
  if (pathname.startsWith('/sources/')) return 'source-detail';
  if (pathname === '/graph' || pathname.startsWith('/graph/')) return 'graph';
  if (pathname === '/code-graph' || pathname.startsWith('/code-graph/')) return 'code-graph';
  if (pathname === '/team') return 'team';
  if (pathname === '/activity') return 'activity';
  return null;
}

/** Route -> that page's probe; unregistered pages return null (no reporting). */
export function resolvePageProbe(pathname: string): PageProbe | null {
  const page = resolvePageName(pathname);
  if (!page) return null;
  return PAGE_PROBES[page] ?? null;
}
