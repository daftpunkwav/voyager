/**
 * @file pageMeta.ts
 * @description Current section title for the top bar (rendered level with the search box).
 *
 * Pages must not repeat the title themselves — this is the single source.
 * Titles reuse the shell nav keys so navigation and page title can never
 * drift apart; the caller (e.g. Topbar via useTranslation) is responsible for
 * re-rendering on languageChanged.
 *
 * Responsibilities:
 * - Map routes to shell nav keys shared with the sidebar labels
 * - Resolve the top bar title through i18n so pages never repeat it
 */

import { i18n } from '@/i18n';

/** Map a route to its nav key (shared with the sidebar labels) or null for unknown paths. */
function navKeyByPath(pathname: string): string | null {
  if (pathname === '/' || pathname.startsWith('/chat')) return 'chat';
  if (pathname === '/team') return 'team';
  if (pathname === '/notes' || pathname.startsWith('/notes')) return 'notes';
  if (pathname === '/sources' || pathname.startsWith('/sources')) return 'sources';
  if (
    pathname === '/graph' ||
    pathname.startsWith('/graph/') ||
    pathname.startsWith('/code-graph')
  ) {
    return 'graph';
  }
  if (pathname === '/overview') return 'overview';
  if (pathname === '/activity') return 'activity';
  if (pathname === '/system/health') return 'health';
  if (pathname === '/usage') return 'usage';
  if (pathname === '/settings') return 'settings';
  return null;
}

export function resolvePageTitle(pathname: string): string {
  const key = navKeyByPath(pathname);
  // shell ships in the initial bundle, so the namespace is always loaded here
  return key ? i18n.t(`shell:nav.${key}`) : '';
}
