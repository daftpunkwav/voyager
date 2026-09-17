/**
 * @file SettingsPage
 * @description Settings page with grouped category navigation: basic (general /
 * appearance / models), agent capabilities (agents / subagents / plugins / mcp /
 * skills / commands / tools), and data & system (health / usage / activity /
 * data / about). Pages retired from the shell (team / usage / activity) are
 * composed here from their building blocks.
 *
 * Responsibilities:
 * - Render the grouped subnav and the active section panel
 * - Compose retired pages (usage / activity) and team blocks into sections
 * - Own GitHub binding and data-export flows; delegated blocks own their state
 */

import { useNavigate } from 'react-router-dom';
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
import { AgentLlmOverridesPanel } from '@/components/settings/llm/AgentLlmOverridesPanel';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { useSettingsStore } from '@/stores/settingsStore';
import { extractErrorMessage } from '@/utils/errors';
import { PRODUCT_NAME } from '@/brand';

import { SettingsIcons } from '@/components/icons/SettingsIcons';
import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';
import { ActivityFeed } from '@/components/activity/ActivityFeed';
import { PersonaGrid } from '@/components/team/PersonaGrid';
import { InstanceList } from '@/components/team/InstanceList';
import { DefinitionGrid } from '@/components/team/DefinitionGrid';
import { SpawnForm } from '@/components/team/SpawnForm';
import { ResumableList } from '@/components/team/ResumableList';
import { ToolCatalog } from '@/components/team/ToolCatalog';
import { PluginsBlock } from '@/components/settings/agent/PluginsBlock';
import { McpBlock } from '@/components/settings/agent/McpBlock';
import { SkillsBlock } from '@/components/settings/agent/SkillsBlock';
import { UserHooksBlock } from '@/components/settings/agent/UserHooksBlock';

type Section =
  | 'general'
  | 'appearance'
  | 'llm'
  | 'agents'
  | 'agentLlm'
  | 'subagents'
  | 'plugins'
  | 'mcp'
  | 'skills'
  | 'commands'
  | 'tools'
  | 'health'
  | 'usage'
  | 'activity'
  | 'data'
  | 'about';

// Labels resolve through settings:nav.<id> at render time so the active
// language applies; icons are stroke glyphs keyed into SettingsIcons.
const NAV_GROUPS: {
  labelKey: string;
  items: { id: Section; icon: keyof typeof SettingsIcons }[];
}[] = [
  {
    labelKey: 'navGroup.basic',
    items: [
      { id: 'general', icon: 'general' },
      { id: 'appearance', icon: 'appearance' },
      { id: 'llm', icon: 'llm' },
    ],
  },
  {
    labelKey: 'navGroup.agent',
    items: [
      { id: 'agents', icon: 'agents' },
      { id: 'agentLlm', icon: 'agentLlm' },
      { id: 'subagents', icon: 'subagents' },
      { id: 'plugins', icon: 'plugins' },
      { id: 'mcp', icon: 'mcp' },
      { id: 'skills', icon: 'skills' },
      { id: 'commands', icon: 'commands' },
      { id: 'tools', icon: 'tools' },
    ],
  },
  {
    labelKey: 'navGroup.system',
    items: [
      { id: 'health', icon: 'health' },
      { id: 'usage', icon: 'usage' },
      { id: 'activity', icon: 'activity' },
      { id: 'data', icon: 'data' },
      { id: 'about', icon: 'about' },
    ],
  },
];

export function SettingsPage() {
  const { t } = useTranslation('settings');
  const navigate = useNavigate();
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
  const [activityKind, setActivityKind] = useState('');
  const [ghPat, setGhPat] = useState('');
  const [unbindId, setUnbindId] = useState<string | null>(null);

  // Language names are autonomous: they never follow the current UI language,
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
          <button type="button" className="subnav-item subnav-back" onClick={() => navigate('/')}>
            <span className="subnav-icon" aria-hidden>
              <SettingsIcons.back />
            </span>
            {t('nav.back')}
          </button>
          <div className="subnav-title">{t('nav.categories')}</div>
          {NAV_GROUPS.map((group) => (
            <div key={group.labelKey} className="subnav-group">
              <div className="subnav-group-label">{t(group.labelKey)}</div>
              {group.items.map((item) => {
                const Icon = SettingsIcons[item.icon];
                return (
                  <button
                    key={item.id}
                    type="button"
                    className={`subnav-item ${section === item.id ? 'active' : ''}`}
                    onClick={() => setSection(item.id)}
                  >
                    <span className="subnav-icon" aria-hidden>
                      <Icon />
                    </span>
                    {t(`nav.${item.id}`)}
                    {item.id === 'llm' && llmAvailability === 'missing' && (
                      <span className="dot-unset" />
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="settings-main">
          {section === 'general' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('general.title')}</h2>
              <section className="settings-group">
                <div className="settings-group-label">GitHub</div>
                {accounts.length > 0 && (
                  <ul className="settings-rows">
                    {accounts.map((a) => (
                      <li key={a.id} className="settings-row">
                        <div className="gh-avatar">{a.username[0]?.toUpperCase()}</div>
                        <div className="gh-meta">
                          <div className="gh-handle">@{a.username}</div>
                          <div className="gh-sub">{t('github.bound')}</div>
                        </div>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => setUnbindId(a.id)}
                        >
                          {t('github.unbind')}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="form-row">
                  <label htmlFor="gh-pat">{t('github.patLabel')}</label>
                  <input
                    id="gh-pat"
                    className="field input"
                    type="password"
                    value={ghPat}
                    onChange={(e) => setGhPat(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="settings-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void bindGithub()}
                  >
                    {t('github.saveAndBind')}
                  </button>
                </div>
              </section>
            </section>
          )}

          {section === 'appearance' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('appearance.title')}</h2>
              <section className="settings-group">
                <div className="settings-group-label">{t('appearance.theme.label')}</div>
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
              </section>

              <section className="settings-group">
                <div className="settings-group-label">{t('appearance.locale.label')}</div>
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
              </section>

              <section className="settings-group">
                <div className="settings-group-head">
                  <div className="settings-group-label">{t('appearance.fontScale.label')}</div>
                  <span className="settings-group-value">{fontScale.toFixed(1)}×</span>
                </div>
                <div className="font-row">
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
                  <div className="font-preview">
                    <div className="fp-sample">
                      <span className="fp-aa">Aa</span>
                      <span className="fp-cn">{t('appearance.fontScale.preview')}</span>
                    </div>
                    <div className="fp-en">The quick brown fox</div>
                  </div>
                </div>
              </section>
            </section>
          )}

          {section === 'llm' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('llm.title')}</h2>
              <LlmSettingsSection />
            </section>
          )}

          {section === 'agents' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('agents.title')}</h2>
              <PersonaGrid />
            </section>
          )}

          {section === 'agentLlm' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('llm.overrides.title')}</h2>
              <AgentLlmOverridesPanel />
            </section>
          )}

          {section === 'subagents' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('subagents.title')}</h2>
              <DefinitionGrid />
              <SpawnForm />
              <InstanceList />
              <ResumableList />
            </section>
          )}

          {section === 'plugins' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('plugins.title')}</h2>
              <PluginsBlock />
            </section>
          )}

          {section === 'mcp' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('mcp.title')}</h2>
              <McpBlock />
            </section>
          )}

          {section === 'skills' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('skills.title')}</h2>
              <SkillsBlock />
            </section>
          )}

          {section === 'commands' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('commands.title')}</h2>
              <UserHooksBlock />
            </section>
          )}

          {section === 'tools' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('tools.title')}</h2>
              <ToolCatalog />
            </section>
          )}

          {section === 'health' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('health.title')}</h2>
              <section className="settings-group">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => navigate('/system/health')}
                >
                  {t('health.open')}
                </button>
              </section>
            </section>
          )}

          {section === 'usage' && (
            <section className="settings-section settings-section--embedded">
              <h2>{t('usage.title')}</h2>
              <LlmUsageDashboard />
            </section>
          )}

          {section === 'activity' && (
            <section className="settings-section settings-section--embedded">
              <h2>{t('activity.title')}</h2>
              <ActivityFeed kind={activityKind} onKindChange={setActivityKind} />
            </section>
          )}

          {section === 'data' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('data.title')}</h2>
              <section className="settings-group">
                <div className="settings-actions">
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => void exportProjects()}
                  >
                    {t('data.exportProjects')}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => void exportNotes()}
                  >
                    {t('data.exportNotes')}
                  </button>
                </div>
              </section>
            </section>
          )}

          {section === 'about' && (
            <section className="settings-section glass-card glass-card--overview-outer">
              <h2>{t('about.title', { name: PRODUCT_NAME })}</h2>
              <section className="settings-group">
                <div className="about-row">
                  <span className="k">{t('about.versionLabel')}</span>
                  <span>v1.0.0</span>
                </div>
                <div className="about-row">
                  <span className="k">{t('about.positioningLabel')}</span>
                  <span>{t('about.positioning')}</span>
                </div>
              </section>
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
