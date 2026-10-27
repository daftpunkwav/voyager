/**
 * @file SettingsSectionPanel
 * @description The shell a settings section renders in.
 *
 * Responsibilities:
 * - Render the heading of the active section and the card chrome around it
 * - Resolve the heading from the section catalog, so the copy follows the
 *   active language
 *
 * Constraints:
 * - The catalog decides the variant: a section listed as embedded renders
 *   without the card chrome.
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { SECTIONS, type SettingsSection } from './sectionCatalog';

interface SettingsSectionPanelProps {
  /** The section the panel renders. */
  section: SettingsSection;
  /** The content of the section. */
  children: ReactNode;
}

export function SettingsSectionPanel({ section, children }: SettingsSectionPanelProps) {
  const { t } = useTranslation('settings');
  const meta = SECTIONS[section];
  return (
    <section
      className={
        meta.embedded
          ? 'settings-section settings-section--embedded'
          : 'settings-section glass-card glass-card--overview-outer'
      }
    >
      <h2>{t(meta.titleKey, meta.titleValues)}</h2>
      {children}
    </section>
  );
}
