/**
 * @file SettingsNav
 * @description Grouped category navigation of the settings page.
 *
 * Responsibilities:
 * - Render the back entry, the group titles and the section entries
 * - Mark the active section and flag a missing LLM provider
 *
 * Constraints:
 * - Labels resolve through the settings namespace at render time, so the
 *   active language applies.
 */

import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { SettingsIcons } from '@/components/icons/SettingsIcons';
import { useLlmAvailable } from '@/hooks/useLlmAvailable';

import { NAV_GROUPS, SECTIONS, type SettingsSection } from './sectionCatalog';

interface SettingsNavProps {
  /** The section the page shows. */
  section: SettingsSection;
  /** Switch to another section. */
  onSelect: (section: SettingsSection) => void;
}

export function SettingsNav({ section, onSelect }: SettingsNavProps) {
  const { t } = useTranslation('settings');
  const navigate = useNavigate();
  // 'missing' = confirmed no usable provider/key (useLlmAvailable probes the llm.*
  // source of truth); 'checking'/'unknown' never flash the dot to avoid flicker.
  const llmAvailability = useLlmAvailable();

  return (
    <nav className="subnav" aria-label={t('nav.aria')}>
      <button type="button" className="subnav-item subnav-back" onClick={() => void navigate('/')}>
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
            const Icon = SettingsIcons[SECTIONS[item].icon];
            return (
              <button
                key={item}
                type="button"
                className={`subnav-item ${section === item ? 'active' : ''}`}
                onClick={() => onSelect(item)}
              >
                <span className="subnav-icon" aria-hidden>
                  <Icon />
                </span>
                {t(`nav.${item}`)}
                {item === 'llm' && llmAvailability === 'missing' && <span className="dot-unset" />}
              </button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}
