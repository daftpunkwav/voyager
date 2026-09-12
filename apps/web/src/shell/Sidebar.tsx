/**
 * @file Sidebar.tsx
 * @description Sidebar navigation grouped into Agent / domain / system sections.
 *
 * Items light up per release stage; anything not yet available stays off the
 * navigation. Detail routes fall back to highlighting their parent nav item.
 * Labels come from the shell namespace and follow the UI language.
 *
 * Responsibilities:
 * - Group navigation into agent / domain / system sections with shared icons
 * - Highlight the active route, falling back to the parent item on detail pages
 * - Show the current user in the footer and support the collapsed layout
 */
import { Link, NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { NavIcons } from '@/components/icons/NavIcons';
import { userInitials } from '@/utils/user';
import { useUIStore } from '@/stores/uiStore';
import { PRODUCT_NAME } from '@/brand';
import { routes } from '@/utils/routes';

/** Nav groups: Agent / domain / system (lit up per release stage; unavailable entries stay off the nav). */
const NAV_ITEMS = [
  // —— Agent mainline ——
  { key: 'chat', path: routes.chat, badge: 'AI' as const, group: 'agent' },
  { key: 'team', path: routes.team, badge: null, group: 'agent' },
  // —— Domain ——
  { key: 'notes', path: routes.notes, badge: null, group: 'domain' },
  { key: 'sources', path: routes.sources, badge: null, group: 'domain' },
  { key: 'graph', path: routes.graph, badge: null, group: 'domain' },
  // —— System ——
  { key: 'overview', path: routes.overview, badge: null, group: 'system' },
  { key: 'health', path: routes.health, badge: null, group: 'system' },
  { key: 'activity', path: routes.activity, badge: null, group: 'system' },
  { key: 'usage', path: routes.usage, badge: null, group: 'system' },
  { key: 'settings', path: routes.settings, badge: null, group: 'system' },
] as const;

export type SidebarPageKey = (typeof NAV_ITEMS)[number]['key'] | 'source-detail' | 'session-detail';

interface SidebarProps {
  /** Currently highlighted page (project detail / chat detail fall back to their parent nav item) */
  activePage?: SidebarPageKey;
}

export function Sidebar({ activePage }: SidebarProps) {
  const { t } = useTranslation('shell');
  const user = useAuthStore((s) => s.user);
  const initials = userInitials(user?.username);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);

  // Render grouped by group
  const groups: Array<{ label: string; keys: string[] }> = [
    { label: t('nav.group.agent'), keys: ['chat', 'team'] },
    { label: t('nav.group.domain'), keys: ['notes', 'sources', 'graph'] },
    { label: t('nav.group.system'), keys: ['overview', 'health', 'activity', 'usage', 'settings'] },
  ];

  return (
    <aside className={`sidebar${collapsed ? ' is-collapsed' : ''}`}>
      <div className="sidebar-brand">
        <div className="sidebar-logo" title={PRODUCT_NAME}>
          {PRODUCT_NAME.slice(0, 1)}
        </div>
        {!collapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.2 }}>
            <span className="sidebar-name">{PRODUCT_NAME}</span>
            <span className="sidebar-version">v1.0.0</span>
          </div>
        )}
      </div>

      {groups.map((g) => {
        const items = NAV_ITEMS.filter((it) => g.keys.includes(it.key));
        if (items.length === 0) return null;
        return (
          <nav className="sidebar-section" key={g.keys.join('-')}>
            {!collapsed && <div className="label">{g.label}</div>}
            {items.map((item) => {
              const Icon = (NavIcons as Record<string, (p: unknown) => React.ReactElement>)[
                item.key
              ];
              const label = t(`nav.${item.key}`);
              const isFallback =
                (activePage === 'source-detail' && item.key === 'sources') ||
                (activePage === 'session-detail' && item.key === 'chat');
              return (
                <NavLink
                  key={item.key}
                  to={item.path}
                  end={item.path === '/'}
                  title={label}
                  className={({ isActive }) => {
                    const active = isActive || isFallback;
                    const classes = ['nav-item'];
                    if (active) classes.push('active');
                    if (item.badge === 'AI') classes.push('ai-badge');
                    return classes.join(' ');
                  }}
                  data-nav-key={item.key}
                >
                  {Icon ? <Icon /> : null}
                  {!collapsed && <span>{label}</span>}
                  {!collapsed && item.badge === 'AI' && <span className="nav-badge">AI</span>}
                </NavLink>
              );
            })}
          </nav>
        );
      })}

      <div className="sidebar-footer">
        <Link className="sidebar-user" to={routes.team} title={user?.username ?? t('user.guest')}>
          <div className="avatar" aria-hidden>
            {initials}
          </div>
          {!collapsed && (
            <div className="sidebar-user__meta">
              <span className="sidebar-user__name">{user?.username ?? t('user.guest')}</span>
              <span className="sidebar-user__hint">{t('user.localHint')}</span>
            </div>
          )}
        </Link>
      </div>
    </aside>
  );
}
