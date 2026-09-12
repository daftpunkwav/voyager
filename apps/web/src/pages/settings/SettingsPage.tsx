/**
 * @file SettingsPage
 * @description Settings page with category navigation: appearance, GitHub binding, LLM, agent, data export, and about.
 *
 * Sections render only after settings have loaded; a backend failure shows a
 * degraded state with a retry entry instead of a blank page.
 *
 * Responsibilities:
 * - Gate rendering on the settings schema load, with loading and degraded
 *   states plus retry
 * - Compose the six sections: appearance, GitHub binding, LLM, agent,
 *   data export, and about
 * - Handle the GitHub token bind/unbind flow and JSON data export with
 *   toast feedback
 */

import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSettings } from '@/hooks/useSettings';
import { useTheme } from '@/hooks/useTheme';
import { useLocale } from '@/hooks/useLocale';
import { useLlmAvailable } from '@/hooks/useLlmAvailable';
import { useGithubAccounts } from '@/hooks/useGithub';
import { setGithubToken, unbindGithub as unbindGithubAccount } from '@/api/auth';
import { exportProjects as exportProjectsApi } from '@/api/projects';
import { listAllNotes } from '@/api/notes';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LlmSettingsSection } from '@/components/settings/LlmSettingsSection';
import { AgentSettingsSection } from '@/components/settings/AgentSettingsSection';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { useSettingsStore } from '@/stores/settingsStore';
import { extractErrorMessage } from '@/utils/errors';
import { PRODUCT_NAME } from '@/brand';

type Section = 'appearance' | 'github' | 'llm' | 'agent' | 'data' | 'about';

// Labels resolve through settings:nav.<id> at render time so the active
// language applies (nav.github/llm/agent are identity strings in both locales).
const NAV: { id: Section; icon: string }[] = [
  { id: 'appearance', icon: '◐' },
  { id: 'github', icon: '⌂' },
  { id: 'llm', icon: '◇' },
  { id: 'agent', icon: '◎' },
  { id: 'data', icon: '▤' },
  { id: 'about', icon: 'i' },
];

export function SettingsPage() {
  const { t } = useTranslation('settings');
  const { settings, isLoading } = useSettings();
  const error = useSettingsStore((s) => s.error);
  const loadSettings = useSettingsStore((s) => s.loadSettings);
  const { theme, changeTheme, changeFontScale, fontScale, setFontScale } = useTheme();
  const { locale, changeLocale } = useLocale();
  // 'missing' = confirmed no usable provider/key (useLlmAvailable probes the llm.*
  // source of truth); 'checking'/'unknown' never flash the dot to avoid flicker.
  const llmAvailability = useLlmAvailable();
  const { data: accounts = [], refetch: refetchAccounts } = useGithubAccounts();
  const addToast = useUIStore((s) => s.addToast);
  const [section, setSection] = useState<Section>('appearance');
  const [ghUser, setGhUser] = useState('');
  const [ghPat, setGhPat] = useState('');
  const [unbindId, setUnbindId] = useState<string | null>(null);

  // Language names are autonomys: they never follow the current UI language,
  // so users can always find their own language (design §8.4).
  const LOCALE_CARDS = [
    { id: 'zh-CN', name: t('appearance.locale.zhCN') },
    { id: 'en', name: t('appearance.locale.en') },
    { id: 'system', name: t('appearance.locale.system') },
  ] as const;

  // Show the spinner only while settings have never loaded. Gating on isLoading
  // alone would stall forever when the backend errors out (isLoading=false but
  // settings still null), leaving no way to reach the degraded UI below.
  if (isLoading && !settings) {
    return (
      <div className="page-scaffold">
        <LoadingSpinner label={t('page.loading')} />
      </div>
    );
  }
  if (!settings) {
    // Backend unreachable: show a degraded state with a retry entry instead of a blank screen
    return (
      <div className="page-scaffold">
        <div className="page-scaffold__state">
          <EmptyState
            title={t('page.loadFailedTitle')}
            description={error ?? t('page.loadFailedDesc')}
            icon={EmptyStateIcons.settings}
            onRetry={() => void loadSettings()}
          />
        </div>
      </div>
    );
  }

  const bindGithub = async () => {
    const token = ghPat.trim();
    if (!token) {
      addToast({ type: 'warning', message: t('github.patRequired') });
      return;
    }
    try {
      // Bind by pasting the token directly (sources.set_github_token); local single-user setup, no OAuth flow
      await setGithubToken(token);
      setGhPat('');
      addToast({ type: 'success', message: t('github.tokenSaved') });
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('github.saveFailed'),
      });
    }
  };

  const unbindGithub = async (_id: string) => {
    // api/auth.unbindGithub is a single-user local stub (no account entity); the id is ignored by the facade
    await unbindGithubAccount();
    void refetchAccounts();
    addToast({ type: 'success', message: t('github.unbound') });
  };

  const exportProjects = async () => {
    const rows = await exportProjectsApi();
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'projects-export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportNotes = async () => {
    const notes = await listAllNotes();
    const blob = new Blob([JSON.stringify(notes, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'notes-export.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-scaffold settings-page">
      <div className="settings-shell">
        <nav className="subnav" aria-label={t('nav.aria')}>
          <div className="subnav-title">{t('nav.categories')}</div>
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`subnav-item ${section === item.id ? 'active' : ''}`}
              onClick={() => setSection(item.id)}
            >
              <span className="subnav-icon" aria-hidden>
                {item.icon}
              </span>
              {t(`nav.${item.id}`)}
              {item.id === 'llm' && llmAvailability === 'missing' && <span className="dot-unset" />}
            </button>
          ))}
        </nav>

        <div className="settings-main">
          {section === 'appearance' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('appearance.title')}</h2>
              <p className="section-desc">{t('appearance.desc')}</p>
              <div className="theme-cards">
                {(['light', 'dark', 'system'] as const).map((th) => (
                  <button
                    key={th}
                    type="button"
                    className={`theme-card ${theme === th ? 'active' : ''}`}
                    onClick={() => {
                      // Sole theme write path: set_theme persists to the store (including
                      // "system") and the selected state is written back only on success.
                      // Must not go through updateSettings — it would pass {theme} into
                      // set_setting and misalign the parameters.
                      changeTheme(th).catch((err) => {
                        addToast({
                          type: 'error',
                          message: t('toast.themeSaveFailed', {
                            message: extractErrorMessage(err),
                          }),
                        });
                      });
                    }}
                  >
                    <div className={`theme-preview pv-${th === 'system' ? 'auto' : th}`}>
                      <div className="pv-side">
                        <i className="on" />
                        <i />
                        <i />
                      </div>
                      <div className="pv-body">
                        <i className="t" />
                        <i />
                      </div>
                    </div>
                    <div className="theme-card-label">
                      {th === 'light'
                        ? t('appearance.theme.light')
                        : th === 'dark'
                          ? t('appearance.theme.dark')
                          : t('appearance.theme.system')}
                      <span className="theme-card-check">✓</span>
                    </div>
                  </button>
                ))}
              </div>

              <div className="form-row" style={{ marginTop: 24 }}>
                <span className="field-label">{t('appearance.locale.label')}</span>
                <div className="theme-cards">
                  {LOCALE_CARDS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`theme-card ${locale === item.id ? 'active' : ''}`}
                      data-testid={`locale-card-${item.id}`}
                      onClick={() => {
                        // Sole locale write path, symmetric to the theme cards: persist via
                        // set_setting first; shell/localeBridge applies store + html[lang]
                        // + i18n only after success.
                        changeLocale(item.id).catch((err) => {
                          addToast({
                            type: 'error',
                            message: t('toast.localeSaveFailed', {
                              message: extractErrorMessage(err),
                            }),
                          });
                        });
                      }}
                    >
                      <div className="theme-card-label">
                        {item.name}
                        <span className="theme-card-check">✓</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>

              <div className="font-row" style={{ marginTop: 24 }}>
                <div className="font-slider-block form-row">
                  <label className="field-label">
                    {t('appearance.fontScale.label')}{' '}
                    <span className="val">{fontScale.toFixed(1)}×</span>
                  </label>
                  <input
                    type="range"
                    className="slider"
                    min={0.8}
                    max={1.5}
                    step={0.1}
                    value={fontScale}
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      // Immediate visual feedback via the store (applies the CSS var);
                      // persistence goes through set_theme (sole font_scale write path,
                      // same capability the theme bridge syncs from). A failed save
                      // toasts but does not snap the slider back mid-drag.
                      setFontScale(v);
                      void changeFontScale(v).catch((err) => {
                        addToast({
                          type: 'error',
                          message: t('appearance.fontScale.saveFailed', {
                            message: extractErrorMessage(err),
                          }),
                        });
                      });
                    }}
                  />
                </div>
                <div className="font-preview">
                  <div className="fp-sample">
                    <span className="fp-aa">Aa</span>
                    <span className="fp-cn">{t('appearance.fontScale.preview')}</span>
                  </div>
                  <div className="fp-en">The quick brown fox</div>
                </div>
              </div>
            </section>
          )}

          {section === 'github' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>GitHub</h2>
              <p className="section-desc">{t('github.desc')}</p>
              {accounts.map((a) => (
                <div key={a.id} className="gh-card" style={{ marginBottom: 16 }}>
                  <div className="gh-avatar">{a.username[0]?.toUpperCase()}</div>
                  <div className="gh-meta">
                    <div className="gh-handle">@{a.username}</div>
                    <div className="gh-sub">{t('github.bound')}</div>
                  </div>
                  <div className="gh-actions">
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={() => setUnbindId(a.id)}
                    >
                      {t('github.unbind')}
                    </button>
                  </div>
                </div>
              ))}
              <div className="form-row">
                <label>{t('github.username')}</label>
                <input
                  className="field input"
                  value={ghUser}
                  onChange={(e) => setGhUser(e.target.value)}
                />
              </div>
              <div className="form-row">
                <label>Personal Access Token</label>
                <input
                  className="field input"
                  type="password"
                  value={ghPat}
                  onChange={(e) => setGhPat(e.target.value)}
                />
              </div>
              <button type="button" className="btn btn-primary" onClick={() => void bindGithub()}>
                {t('github.saveAndBind')}
              </button>
            </section>
          )}

          {section === 'llm' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('llm.title')}</h2>
              <p className="section-desc">{t('llm.desc')}</p>
              <LlmSettingsSection />
              <p style={{ marginTop: 12, fontSize: 13 }}>
                <Link to="/usage" style={{ color: 'var(--brand-500)' }}>
                  {t('llm.viewUsage')}
                </Link>
              </p>
            </section>
          )}

          {section === 'agent' && <AgentSettingsSection />}

          {section === 'data' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('data.title')}</h2>
              <p className="section-desc">{t('data.desc')}</p>
              <button
                type="button"
                className="btn btn-primary"
                style={{ marginRight: 8 }}
                onClick={() => void exportProjects()}
              >
                {t('data.exportProjects')}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => void exportNotes()}>
                {t('data.exportNotes')}
              </button>
            </section>
          )}

          {section === 'about' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('about.title', { name: PRODUCT_NAME })}</h2>
              <div className="about-row">
                <span className="k">{t('about.versionLabel')}</span>
                <span>v1.0.0</span>
              </div>
              <div className="about-row">
                <span className="k">{t('about.positioningLabel')}</span>
                <span>{t('about.positioning')}</span>
              </div>
            </section>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={unbindId !== null}
        title={t('github.unbindTitle')}
        message={t('github.unbindConfirm')}
        danger
        onConfirm={() => {
          if (unbindId) void unbindGithub(unbindId);
          setUnbindId(null);
        }}
        onCancel={() => setUnbindId(null)}
      />
    </div>
  );
}
