/**
 * @file SettingsPage
 * @description Settings page with grouped category navigation: basic (general /
 * appearance / models), agent capabilities (agents / subagents / plugins / mcp /
 * skills / commands / tools), and data & system (health / usage / activity /
 * data / about). Pages retired from the shell (team / usage / activity) are
 * composed here from their building blocks.
 *
 * Responsibilities:
 * - Gate the page on the settings load and show the degraded state
 * - Render the grouped subnav and the active section panel
 *
 * Constraints:
 * - The section ids live in sectionCatalog, the panels in ./sections: this
 *   module holds the page shell only.
 */

import { useTranslation } from 'react-i18next';

import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useSettings } from '@/hooks/useSettings';
import { useSettingsStore } from '@/stores/settingsStore';

import { SettingsNav } from './SettingsNav';
import { SettingsPanel } from './SettingsPanel';
import { useSettingsSection } from './useSettingsSection';

export function SettingsPage() {
  const { t } = useTranslation('settings');
  const { settings, isLoading } = useSettings();
  const error = useSettingsStore((s) => s.error);
  const loadSettings = useSettingsStore((s) => s.loadSettings);
  const { section, setSection } = useSettingsSection();

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

  return (
    <div className="page-scaffold settings-page">
      <div className="settings-shell">
        <SettingsNav section={section} onSelect={setSection} />

        <div className="settings-main">
          <SettingsPanel section={section} />
        </div>
      </div>
    </div>
  );
}
