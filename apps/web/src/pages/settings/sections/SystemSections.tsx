/**
 * @file SystemSections
 * @description The data & system group of the settings page: the health
 * entry, the usage dashboard, the activity feed, the data export, the
 * domain settings and the about panel.
 *
 * Responsibilities:
 * - Compose the retired pages (usage / activity) into section panels
 * - Export the projects and the notes as JSON downloads
 *
 * Constraints:
 * - The export reads through the api modules and downloads a JSON blob; this
 *   module must not call the backend directly.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { listAllNotes } from '@/api/notes';
import { exportProjects as exportProjectsApi } from '@/api/projects';
import { ActivityFeed } from '@/components/activity/ActivityFeed';
import { DynamicSettingsGroup } from '@/components/settings/dynamic/DynamicSettingsGroup';
import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';
import { useUIStore } from '@/stores/uiStore';
import { PRODUCT_NAME } from '@/brand';

/** The entry to the health page. */
export function HealthSection() {
  const { t } = useTranslation('settings');
  const navigate = useNavigate();
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('health.title')}</h2>
      <section className="settings-group">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => void navigate('/system/health')}
        >
          {t('health.open')}
        </button>
      </section>
    </section>
  );
}

/** The usage dashboard (a page retired from the shell). */
export function UsageSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section settings-section--embedded">
      <h2>{t('usage.title')}</h2>
      <LlmUsageDashboard />
    </section>
  );
}

/** The activity feed (a page retired from the shell). */
export function ActivitySection() {
  const { t } = useTranslation('settings');
  const [activityKind, setActivityKind] = useState('');
  return (
    <section className="settings-section settings-section--embedded">
      <h2>{t('activity.title')}</h2>
      <ActivityFeed kind={activityKind} onKindChange={setActivityKind} />
    </section>
  );
}

/** The data export. */
export function DataSection() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const downloadJson = (payload: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportProjects = async () => {
    try {
      downloadJson(await exportProjectsApi(), 'projects-export.json');
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('data.exportFailed'),
      });
    }
  };

  const exportNotes = async () => {
    try {
      downloadJson(await listAllNotes(), 'notes-export.json');
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('data.exportFailed'),
      });
    }
  };

  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('data.title')}</h2>
      <section className="settings-group">
        <div className="settings-actions">
          <button type="button" className="btn btn-primary" onClick={() => void exportProjects()}>
            {t('data.exportProjects')}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => void exportNotes()}>
            {t('data.exportNotes')}
          </button>
        </div>
      </section>
    </section>
  );
}

/** The domain settings (services, notes, observability, system). */
export function DomainsSection() {
  const { t } = useTranslation('settings');
  return (
    <section className="settings-section glass-card glass-card--overview-outer">
      <h2>{t('domains.title')}</h2>
      <DynamicSettingsGroup
        modules={['gateway', 'graph', 'sources', 'browser', 'code_exec', 'office']}
        titleKey="domains.services"
      />
      <DynamicSettingsGroup
        prefixes={[
          'notes.sort.',
          'notes.list.',
          'notes.editor.',
          'notes.trash.',
          'notes.history.',
          'notes.export.',
          'notes.assets.',
        ]}
        titleKey="domains.notes"
      />
      <DynamicSettingsGroup
        prefixes={['agent.observability.', 'agent.evaluation.']}
        titleKey="domains.observability"
      />
      <DynamicSettingsGroup prefixes={['host.domains.']} titleKey="domains.system" />
    </section>
  );
}

/** The about panel. */
export function AboutSection() {
  const { t } = useTranslation('settings');
  return (
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
  );
}
