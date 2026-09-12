/**
 * @file Topbar.tsx
 * @description Top bar: page title, global search (Ctrl/Cmd+K), theme toggle,
 * GitHub binding indicator, activity notifications, help, and avatar.
 *
 * Theme toggling is the single write path: it persists set_theme first, then
 * updates the selected state and visuals via useTheme. The toggle direction
 * follows the visible DOM data-theme, so an unsynced store never causes a
 * "first click does nothing" moment.
 *
 * Responsibilities:
 * - Resolve and render the current page title via pageMeta
 * - Focus search on Ctrl / Cmd+K and navigate to sources on Enter
 * - Toggle theme through the single persist-first write path
 * - Provide the GitHub binding indicator, activity, help popover and avatar entries
 */
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useUIStore } from '@/stores/uiStore';
import { userInitials } from '@/utils/user';
import { routes } from '@/utils/routes';
import { resolvePageTitle } from '@/shell/pageMeta';
import { extractErrorMessage } from '@/utils/errors';
import { useTheme } from '@/hooks/useTheme';

function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform) || /Mac OS X/.test(navigator.userAgent);
}

export function Topbar() {
  // useTranslation subscribes this component to languageChanged, so the
  // resolvePageTitle() result below re-renders when the UI language switches.
  const { t } = useTranslation('shell');
  const user = useAuthStore((s) => s.user);
  const theme = useUIStore((s) => s.theme);
  const addToast = useUIStore((s) => s.addToast);
  const { changeTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const searchRef = useRef<HTMLInputElement>(null);
  const helpRef = useRef<HTMLDivElement>(null);
  const initials = userInitials(user?.username);
  const [helpOpen, setHelpOpen] = useState(false);
  const [modKey, setModKey] = useState('Ctrl+K');

  const [systemDark, setSystemDark] = useState<boolean>(readSystemPrefersDark);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const update = () => setSystemDark(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);
  const isDark = theme === 'dark' || (theme === 'system' && systemDark);

  useEffect(() => {
    setModKey(isApplePlatform() ? '⌘K' : 'Ctrl+K');
  }, []);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!helpOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (helpRef.current && !helpRef.current.contains(e.target as Node)) {
        setHelpOpen(false);
      }
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape') setHelpOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      window.removeEventListener('keydown', onKey);
    };
  }, [helpOpen]);

  const onSearchKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      const q = searchRef.current?.value.trim() ?? '';
      navigate(q ? `${routes.sources}?q=${encodeURIComponent(q)}` : routes.sources);
    }
  };

  // Single theme write path: persist via set_theme first, then update the selected
  // state and visuals via useTheme on success.
  // The toggle direction follows what is visible (DOM data-theme): the store being
  // briefly out of sync never causes a "first click does nothing" moment.
  const toggleTheme = () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    changeTheme(next).catch((err) => {
      addToast({
        type: 'error',
        message: t('theme.toggleFailed', { message: extractErrorMessage(err) }),
      });
    });
  };

  const pageTitle = resolvePageTitle(location.pathname);

  return (
    <header className="topbar">
      {pageTitle ? <h1 className="topbar-title">{pageTitle}</h1> : null}
      <div className="topbar-spacer" />
      <div className="topbar-search">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width={14}
          height={14}
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          ref={searchRef}
          type="text"
          role="searchbox"
          placeholder={t('search.placeholder')}
          autoComplete="off"
          aria-label={t('search.aria')}
          onKeyDown={onSearchKey}
        />
        <kbd>{modKey}</kbd>
      </div>
      {user?.github_login && (
        <span className="gh-bound" title={t('github.boundTitle')}>
          <svg viewBox="0 0 24 24" fill="currentColor" width={14} height={14} aria-hidden>
            <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.92.58.11.79-.25.79-.56v-2c-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.69-1.28-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.78 1.19 1.78 1.19 1.04 1.78 2.72 1.27 3.38.97.1-.75.4-1.27.74-1.56-2.55-.29-5.24-1.28-5.24-5.7 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.04 0 0 .97-.31 3.18 1.18.92-.26 1.91-.39 2.89-.39.98 0 1.97.13 2.89.39 2.21-1.49 3.18-1.18 3.18-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.84 1.18 3.1 0 4.43-2.7 5.41-5.26 5.69.41.36.78 1.06.78 2.13v3.16c0 .31.21.68.8.56C20.21 21.38 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
          </svg>
          @{user.github_login}
        </span>
      )}
      <button
        type="button"
        className="topbar-action"
        title={t('theme.toggleTitle')}
        aria-label={t('theme.toggleAria')}
        onClick={toggleTheme}
      >
        {isDark ? (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width={16}
            height={16}
            aria-hidden
          >
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        ) : (
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width={16}
            height={16}
            aria-hidden
          >
            <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
          </svg>
        )}
      </button>
      <button
        type="button"
        className="topbar-action"
        title={t('activity.title')}
        aria-label={t('activity.openAria')}
        onClick={() => navigate(routes.activity)}
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          width={16}
          height={16}
          aria-hidden
        >
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.7 21a2 2 0 0 1-3.4 0" />
        </svg>
      </button>
      <div className="topbar-help" ref={helpRef}>
        <button
          type="button"
          className="topbar-action"
          title={t('help.title')}
          aria-label={t('help.aria')}
          aria-expanded={helpOpen}
          aria-haspopup="dialog"
          onClick={() => setHelpOpen((v) => !v)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width={16}
            height={16}
            aria-hidden
          >
            <circle cx="12" cy="12" r="9" />
            <path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.5-2.5 2-2.5 3.5" />
            <circle cx="12" cy="17" r="0.8" fill="currentColor" />
          </svg>
        </button>
        {helpOpen ? (
          <div className="topbar-help__panel" role="dialog" aria-label={t('help.panelAria')}>
            <h4>{t('help.panelAria')}</h4>
            <p>
              <span>{t('help.focusSearch')}</span>
              <kbd>{modKey}</kbd>
            </p>
            <p>
              <span>{t('help.closeDrawers')}</span>
              <kbd>Esc</kbd>
            </p>
            <p>
              <span>{t('help.activityStream')}</span>
              <kbd>{t('help.bell')}</kbd>
            </p>
          </div>
        ) : null}
      </div>
      <button
        type="button"
        className="topbar-action"
        title={t('profile.title')}
        aria-label={t('profile.aria')}
        style={{ display: 'grid', placeItems: 'center' }}
        onClick={() => navigate(routes.team)}
      >
        <div className="avatar" style={{ width: 28, height: 28, fontSize: 11 }}>
          {initials}
        </div>
      </button>
    </header>
  );
}
