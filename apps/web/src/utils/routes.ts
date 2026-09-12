/**
 * @file routes
 * @description Single source of truth for frontend route paths. Legacy aliases
 * (/projects, /agent, /graph/projects) are redirected by App.
 */

export const routes = {
  chat: '/',
  chatSession: (id: string) => `/chat/${encodeURIComponent(id)}`,
  team: '/team',
  notes: '/notes',
  note: (id: string, project?: string) => {
    const q = new URLSearchParams({ note: id });
    if (project) q.set('project', project);
    return `/notes?${q.toString()}`;
  },
  sources: '/sources',
  sourceRepo: (id: string) => `/sources/repo/${encodeURIComponent(id)}`,
  sourceDoc: (id: string) => `/sources/doc/${encodeURIComponent(id)}`,
  sourceWeb: (id: string) => `/sources/web/${encodeURIComponent(id)}`,
  /** Route graph-node / activity entries to the matching resource detail page by kind. */
  sourceOf: (kind: string | undefined, id: string) => {
    if (kind === 'doc') return `/sources/doc/${encodeURIComponent(id)}`;
    if (kind === 'web') return `/sources/web/${encodeURIComponent(id)}`;
    return `/sources/repo/${encodeURIComponent(id)}`;
  },
  graph: '/graph',
  codeGraph: (id: string) => `/code-graph/${encodeURIComponent(id)}`,
  overview: '/overview',
  activity: '/activity',
  health: '/system/health',
  usage: '/usage',
  settings: '/settings',
} as const;
