/**
 * @file BasicSections
 * @description The basic group of the settings page: the GitHub binding, the
 * appearance controls (theme, language, font scale) and the model config.
 *
 * Responsibilities:
 * - Bind and unbind the GitHub account through the auth facade
 * - Write theme, language and font scale through their single write paths
 * - Compose the model configuration section
 *
 * Constraints:
 * - Every write goes through the capability facade or the api modules; this
 *   module must not call the backend directly.
 * - The appearance values persist first and the selection follows on success;
 *   a failed write toasts and leaves the selection untouched.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { setGithubToken, unbindGithub as unbindGithubAccount } from '@/api/auth';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { DynamicSettingsGroup } from '@/components/settings/dynamic/DynamicSettingsGroup';
import { LlmSettingsSection } from '@/components/settings/LlmSettingsSection';
import { useGithubAccounts } from '@/hooks/useGithub';
import { useLocale } from '@/hooks/useLocale';
import { useTheme } from '@/hooks/useTheme';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';

/** GitHub binding: the bound account and the token to bind a new one. */
export function GeneralSection() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const { data: accounts = [], refetch: refetchAccounts } = useGithubAccounts();
  const [ghPat, setGhPat] = useState('');
  const [unbindId, setUnbindId] = useState<string | null>(null);

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

  return (
    <>
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
            <button type="button" className="btn btn-primary" onClick={() => void bindGithub()}>
              {t('github.saveAndBind')}
            </button>
          </div>
        </section>
      </section>

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
    </>
  );
}

/** Appearance: theme, language and font scale. */
export function AppearanceSection() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const { theme, changeTheme, changeFontScale, fontScale, setFontScale } = useTheme();
  const { locale, changeLocale } = useLocale();

  // Language names are autonomous: they never follow the current UI language,
  // so users can always find their own language.
  const localeCards = [
    { id: 'zh-CN', name: t('appearance.locale.zhCN') },
    { id: 'en', name: t('appearance.locale.en') },
    { id: 'system', name: t('appearance.locale.system') },
  ] as const;

  return (
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
                changeTheme(th).catch((err: unknown) => {
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
          {localeCards.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`theme-card ${locale === item.id ? 'active' : ''}`}
              data-testid={`locale-card-${item.id}`}
              onClick={() => {
                // Sole locale write path, symmetric to the theme cards: persist via
                // set_setting first; shell/localeBridge applies store + html[lang]
                // + i18n only after success.
                changeLocale(item.id).catch((err: unknown) => {
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
              void changeFontScale(v).catch((err: unknown) => {
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

      <DynamicSettingsGroup modules={['appearance', 'privacy']} />
    </section>
  );
}

/** Model configuration: the provider rail plus the schema-driven llm rows. */
export function LlmSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('llm.title')}</h2>
      <LlmSettingsSection />
      <DynamicSettingsGroup modules={['llm']} titleKey="llm.dynamics" />
    </section>
  );
}
