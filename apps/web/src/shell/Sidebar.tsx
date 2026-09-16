/**
 * @file Sidebar.tsx
 * @description Sidebar: brand mark (click to open the overview page) with a
 * rail collapse toggle beside it, the three domain nav entries, the chat
 * session list, and the footer quick entries (notifications / settings).
 *
 * Responsibilities:
 * - Highlight the active route, falling back to the parent item on detail pages
 * - Switch / create chat sessions inline (lightweight list; rename/delete stay
 *   in the chat page session drawer)
 * - Keep the footer entries legible when collapsed (icon-only, centered)
 */
import { useEffect, useId, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { NavIcons } from '@/components/icons/NavIcons';
import { useUIStore } from '@/stores/uiStore';
import { useChatStore } from '@/stores/chatStore';
import { loadChatSessions, loadSessionTimeline } from '@/bridge/chatSend';
import { createSession, setActiveSession, type ChatSessionRow } from '@/api/agent';
import { ServiceError } from '@/bridge/client';
import { extractErrorMessage } from '@/utils/errors';
import { PRODUCT_NAME } from '@/brand';
import { routes } from '@/utils/routes';

/** Domain nav entries (system entries live in the footer / settings page). */
const NAV_ITEMS = [
  { key: 'notes', path: routes.notes, group: 'domain' },
  { key: 'sources', path: routes.sources, group: 'domain' },
  { key: 'graph', path: routes.graph, group: 'domain' },
] as const;

export type SidebarPageKey =
  | (typeof NAV_ITEMS)[number]['key']
  | 'chat'
  | 'team'
  | 'settings'
  | 'health'
  | 'usage'
  | 'overview'
  | 'activity'
  | 'source-detail'
  | 'session-detail';

interface SidebarProps {
  /** Currently highlighted page (project detail / chat detail fall back to their parent nav item) */
  activePage?: SidebarPageKey;
}

/**
 * Brand mark: a voyager's trail — the V-shaped flight path fades toward both
 * ends while the lowest point burns brightest, with a small star drifting off
 * the upper tip (it breathes via .sidebar-logo-star in design-system.css).
 */
function BrandLogo() {
  const gradientId = useId();
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#fff" stopOpacity="1" />
        </linearGradient>
      </defs>
      <path
        d="M5.5 5.5 12 19 18.5 8"
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="20" cy="4.8" r="1.8" fill="#fff" className="sidebar-logo-star" />
    </svg>
  );
}

/** Lightweight session list: switch + create only; rename/delete stay in the chat page drawer. */
function SidebarSessions() {
  const { t } = useTranslation('chat');
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const sessions = useChatStore((s) => s.sessions);
  const activeId = useChatStore((s) => s.activeSessionId);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // Silent on failure: the store keeps its previous list (same as chatSend).
    void loadChatSessions();
  }, []);

  const fail = (err: unknown) => {
    addToast({
      type: 'error',
      message: err instanceof ServiceError ? extractErrorMessage(err) : String(err),
    });
  };

  const handleCreate = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await createSession('');
      await loadChatSessions();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const handleSwitch = async (row: ChatSessionRow) => {
    if (busy) return;
    if (row.session_id === activeId) {
      navigate(routes.chat);
      return;
    }
    setBusy(true);
    try {
      await setActiveSession(row.session_id);
      const loaded = useChatStore.getState().switchSession(row.session_id);
      if (!loaded) await loadSessionTimeline(row.session_id);
      navigate(routes.chat);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <nav className="sidebar-section sidebar-sessions" aria-label={t('session.drawerTitle')}>
      <div className="sidebar-sessions__head">
        <span className="label">{t('session.drawerTitle')}</span>
        <button
          type="button"
          className="sidebar-sessions__new"
          title={t('session.new')}
          aria-label={t('session.new')}
          disabled={busy}
          onClick={() => void handleCreate()}
        >
          +
        </button>
      </div>
      <div className="sidebar-sessions__list">
        {sessions.length === 0 ? (
          <div className="sidebar-sessions__empty">{t('session.empty')}</div>
        ) : (
          sessions.map((row) => {
            const isActive = row.session_id === activeId;
            const title = row.title || t('session.untitled');
            return (
              <button
                key={row.session_id}
                type="button"
                className={`sidebar-sessions__item${isActive ? ' is-active' : ''}`}
                disabled={busy}
                title={title}
                onClick={() => void handleSwitch(row)}
              >
                <span className="sidebar-sessions__name">{title}</span>
                {isActive ? <span className="sidebar-sessions__dot" aria-hidden /> : null}
              </button>
            );
          })
        )}
      </div>
    </nav>
  );
}

export function Sidebar({ activePage }: SidebarProps) {
  const { t } = useTranslation('shell');
  const navigate = useNavigate();
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  // Footer quick entries, top to bottom. Notifications is a plain button (it
  // will grow into the notification center; every other page lives in Settings).
  const footerItems = [
    {
      key: 'notifications',
      label: t('notifications.title'),
      path: routes.activity,
      Icon: NavIcons.bell,
    },
    { key: 'settings', label: t('nav.settings'), path: routes.settings, Icon: NavIcons.settings },
  ] as const;

  return (
    <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-head">
        <button
          type="button"
          className="sidebar-brand"
          title={t('nav.overview')}
          aria-label={t('nav.overview')}
          onClick={() => void navigate(routes.overview)}
        >
          <div className="sidebar-logo">
            <BrandLogo />
          </div>
          {!collapsed && <span className="sidebar-name">{PRODUCT_NAME}</span>}
        </button>
        <button
          type="button"
          className="sidebar-collapse"
          title={collapsed ? t('nav.expand') : t('nav.collapse')}
          aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
          aria-expanded={!collapsed}
          onClick={toggleSidebar}
        >
          <NavIcons.panel />
        </button>
      </div>

      <nav className="sidebar-section" aria-label={t('nav.group.domain')}>
        {NAV_ITEMS.map((item) => {
          const Icon = (NavIcons as Record<string, (p: unknown) => React.ReactElement>)[item.key];
          const label = t(`nav.${item.key}`);
          const isFallback = activePage === 'source-detail' && item.key === 'sources';
          return (
            <NavLink
              key={item.key}
              to={item.path}
              title={label}
              className={({ isActive }) => {
                const active = isActive || isFallback;
                const classes = ['nav-item'];
                if (active) classes.push('active');
                return classes.join(' ');
              }}
              data-nav-key={item.key}
            >
              {Icon ? <Icon /> : null}
              {!collapsed && <span>{label}</span>}
            </NavLink>
          );
        })}
      </nav>

      {!collapsed && <SidebarSessions />}

      <div className="sidebar-footer">
        {footerItems.map(({ key, label, path, Icon }) =>
          key === 'notifications' ? (
            <button
              key={key}
              type="button"
              className="sidebar-footer__btn"
              title={label}
              aria-label={label}
              onClick={() => void navigate(path)}
            >
              <Icon />
              {!collapsed && <span>{label}</span>}
            </button>
          ) : (
            <NavLink
              key={key}
              to={path}
              title={label}
              className={({ isActive }) => `sidebar-footer__btn${isActive ? ' is-active' : ''}`}
            >
              <Icon />
              {!collapsed && <span>{label}</span>}
            </NavLink>
          )
        )}
      </div>
    </aside>
  );
}
