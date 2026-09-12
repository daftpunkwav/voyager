/**
 * @file AppShell.tsx
 * @description Application shell: liquid-glass navigation (Sidebar + Topbar),
 * route-aware activePage for the Sidebar, PageProbe, and FloatingChat (hidden
 * on chat routes).
 *
 * Domain side effects (e.g. the notes UI bridge) are assembled and injected
 * as `bridges` by the App root; the shell never imports page-private modules.
 * The .app container always keeps a 2-column layout (Sidebar + main) — never
 * add extra grid columns to it, or the Topbar collapses.
 *
 * Responsibilities:
 * - Keep the two-column shell layout and resolve the active page from the route
 * - Wrap routed content in an ErrorBoundary with a page-level retry fallback
 * - Mount ToastContainer, PageProbe and FloatingChat (hidden on chat routes)
 */

import { type ReactNode } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Sidebar, type SidebarPageKey } from '@/shell/Sidebar';
import { Topbar } from '@/shell/Topbar';
import { ToastContainer } from '@/components/common/ToastContainer';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { EmptyState } from '@/components/common/EmptyState';
import { PageProbe } from '@/widgets/PageProbe';
import { FloatingChat } from '@/widgets/FloatingChat';
import { useUIStore } from '@/stores/uiStore';
import { i18n } from '@/i18n';

export interface AppShellProps {
  /** Optional domain bridges (injected by the route assembly root); the shell itself has zero page-private dependencies. */
  bridges?: ReactNode;
}

function resolveActivePage(pathname: string): SidebarPageKey {
  if (pathname === '/' || pathname.startsWith('/chat')) return 'chat';
  if (pathname === '/team') return 'team';
  if (pathname === '/notes') return 'notes';
  if (pathname === '/sources') return 'sources';
  if (pathname.startsWith('/sources/')) return 'source-detail';
  if (pathname === '/graph' || pathname.startsWith('/code-graph')) return 'graph';
  if (pathname === '/overview') return 'overview';
  if (pathname === '/activity') return 'activity';
  if (pathname === '/system/health') return 'health';
  if (pathname === '/usage') return 'usage';
  if (pathname === '/settings') return 'settings';
  return 'overview';
}

/** Standard app shell: Sidebar + Topbar (search/theme/notifications/avatar) + <Outlet/>
 * + PageProbe + FloatingChat. */
function pageErrorFallback(error: Error, reset: () => void) {
  // Plain function (not a component): hooks are unavailable here, so resolve
  // copy through the i18n instance directly.
  return (
    <div className="page-scaffold">
      <div className="page-scaffold__state">
        <EmptyState
          title={i18n.t('shell:pageError.title')}
          description={error.message || i18n.t('shell:pageError.desc')}
          action={
            <button type="button" className="btn btn-primary" onClick={reset}>
              {i18n.t('common:action.retry')}
            </button>
          }
        />
      </div>
    </div>
  );
}

export function AppShell({ bridges }: AppShellProps) {
  const { t } = useTranslation('shell');
  const { pathname } = useLocation();
  const activePage = resolveActivePage(pathname);
  const sidebarCollapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const onChat = pathname === '/' || pathname.startsWith('/chat');

  return (
    <div className={['app', sidebarCollapsed ? 'sidebar-collapsed' : ''].filter(Boolean).join(' ')}>
      <a className="skip-link" href="#main-content">
        {t('skipToContent')}
      </a>
      <Sidebar activePage={activePage} />
      {/* Sidebar collapse toggle: pinned to the seam between sidebar and main column, vertically fixed; collapse/expand slides horizontally only */}
      <button
        type="button"
        className="sidebar-edge-toggle"
        title={sidebarCollapsed ? t('nav.expand') : t('nav.collapse')}
        aria-label={sidebarCollapsed ? t('nav.expand') : t('nav.collapse')}
        aria-expanded={!sidebarCollapsed}
        data-testid="sidebar-toggle"
        onClick={toggleSidebar}
      >
        <svg
          viewBox="0 0 24 24"
          width={13}
          height={13}
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          {sidebarCollapsed ? <path d="M9 6l6 6-6 6" /> : <path d="M15 6l-6 6 6 6" />}
        </svg>
      </button>
      <div className="main">
        <Topbar />
        <main id="main-content" className="content" tabIndex={-1}>
          <ErrorBoundary key={pathname} fallback={pageErrorFallback}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <ToastContainer />
      <PageProbe />
      {onChat ? null : <FloatingChat />}
      {bridges}
    </div>
  );
}
