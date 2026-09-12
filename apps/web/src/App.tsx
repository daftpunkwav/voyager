/**
 * @file App
 * @description Route table (neutral naming, domain-based directories). Heavy
 * pages (graph/PDF/usage) are lazy-loaded; the chat home is eager for a faster
 * first paint.
 *
 * Legacy paths /projects /agent /graph/projects keep redirects so old
 * bookmarks never land on a 404.
 */

import { lazy, Suspense, useMemo, type ComponentType, type LazyExoticComponent } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { AppShell } from '@/shell/AppShell';
import { ChatPage } from '@/pages/chat/ChatPage';
import { NotesUiBridge } from '@/pages/notes/notesUiBridge';
import { NotFound } from '@/shell/NotFound';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { i18n } from '@/i18n';
import { routes } from '@/utils/routes';
import { useProjectNotes } from '@/hooks/useNotes';
import { useGraph } from '@/hooks/useGraph';
import { sendUserTurn } from '@/bridge/chatSend';
import type { ProjectDetailPorts } from '@/pages/sources/ProjectDetailPage';

/** Shell + domain bridge assembly: removing notes means dropping the bridges prop; AppShell itself has no page-private dependencies. */
function AppShellWithBridges() {
  return <AppShell bridges={<NotesUiBridge />} />;
}

function lazyNamed<P, K extends string>(
  loader: () => Promise<Record<K, ComponentType<P>>>,
  key: K
): LazyExoticComponent<ComponentType<P>> {
  return lazy(async () => {
    const mod = await loader();
    const Comp = mod[key];
    if (!Comp) throw new Error(i18n.t('common:app.pageExportMissing', { key: String(key) }));
    return { default: Comp };
  });
}

const TeamPage = lazyNamed(() => import('@/pages/team/TeamPage'), 'TeamPage');
const NotesPage = lazyNamed(() => import('@/pages/notes/NotesPage'), 'NotesPage');
const SourcesPage = lazyNamed(() => import('@/pages/sources/SourcesPage'), 'SourcesPage');
const ProjectDetailPage = lazyNamed(
  () => import('@/pages/sources/ProjectDetailPage'),
  'ProjectDetailPage'
);
const DocReader = lazyNamed(() => import('@/pages/sources/DocReader'), 'DocReader');
const PageReader = lazyNamed(() => import('@/pages/sources/PageReader'), 'PageReader');
const GraphPage = lazyNamed(() => import('@/pages/graph/GraphPage'), 'GraphPage');
const CodeGraphPage = lazyNamed(() => import('@/pages/code-graph/CodeGraphPage'), 'CodeGraphPage');
const OverviewPage = lazyNamed(() => import('@/pages/overview/OverviewPage'), 'OverviewPage');
const ActivityPage = lazyNamed(() => import('@/pages/activity/ActivityPage'), 'ActivityPage');
const HealthPage = lazyNamed(() => import('@/pages/health/HealthPage'), 'HealthPage');
const UsagePage = lazyNamed(() => import('@/pages/usage/UsagePage'), 'UsagePage');
const SettingsPage = lazyNamed(() => import('@/pages/settings/SettingsPage'), 'SettingsPage');

function RedirectKeepSearch({ to }: { to: string }) {
  const loc = useLocation();
  return <Navigate to={{ pathname: to, search: loc.search, hash: loc.hash }} replace />;
}

function RedirectProject() {
  const { id } = useParams();
  return <Navigate to={id ? routes.sourceRepo(id) : routes.sources} replace />;
}

function RedirectCodeGraph() {
  const { id } = useParams();
  return <Navigate to={id ? routes.codeGraph(id) : routes.graph} replace />;
}

function PageFallback() {
  const { t } = useTranslation('common');
  return <LoadingSpinner fullScreen label={t('common:app.loadingPage')} />;
}

/** Detail-page port assembly: the notes / graph / chat cross-domain lines are
 *  injected here (ProjectDetailPorts) while the sources detail page itself only
 *  consumes sources data; removing a domain only touches this spot. */
function ProjectDetailRoute() {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const { data: notes = [] } = useProjectNotes(id);
  const { data: graphData } = useGraph();
  const ports = useMemo<ProjectDetailPorts>(() => {
    const related = (() => {
      if (!graphData || !id) return [] as { id: string; sim: number }[];
      return graphData.edges
        .filter((e) => e.source === id || e.target === id)
        .map((e) => ({ id: e.source === id ? e.target : e.source, sim: e.similarity }))
        .sort((a, b) => b.sim - a.sim)
        .slice(0, 5);
    })();
    return {
      notes,
      related,
      openProjectNotes: (projectId: string) => navigate(`/notes?project=${projectId}`),
      sendToChat: sendUserTurn,
    };
  }, [notes, graphData, id, navigate]);
  return <ProjectDetailPage {...ports} />;
}

export function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<AppShellWithBridges />}>
          {/* Single-timeline chat: the home route is the conversation; legacy session deep links collapse to /chat */}
          <Route index element={<ChatPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="chat/:sessionId" element={<Navigate to="/chat" replace />} />
          <Route path="agent" element={<RedirectKeepSearch to={routes.chat} />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="notes" element={<NotesPage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="sources/repo/:id" element={<ProjectDetailRoute />} />
          <Route path="sources/doc/:id" element={<DocReader />} />
          <Route path="sources/web/:id" element={<PageReader />} />
          <Route path="sources/:id" element={<ProjectDetailRoute />} />
          <Route path="projects" element={<Navigate to={routes.sources} replace />} />
          <Route path="projects/:id" element={<RedirectProject />} />
          <Route path="graph" element={<GraphPage />} />
          <Route path="graph/projects/:id" element={<RedirectCodeGraph />} />
          <Route path="code-graph" element={<CodeGraphPage />} />
          <Route path="code-graph/:id" element={<CodeGraphPage />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="system/health" element={<HealthPage />} />
          <Route path="usage" element={<UsagePage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
