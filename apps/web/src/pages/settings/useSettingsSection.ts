/**
 * @file useSettingsSection
 * @description Deep-linkable section state of the settings page.
 *
 * Responsibilities:
 * - Keep the active section in sync with the ?section= query parameter
 * - Scrub an unknown section value from the query instead of leaving it next
 *   to a default section
 *
 * Constraints:
 * - The query syncs while mounted, not only at mount: a navigate() to this
 *   same route re-renders without remounting, so an in-page deep link would
 *   otherwise never land.
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { NAV_SECTIONS, type SettingsSection } from './sectionCatalog';

export interface SettingsSectionState {
  /** The section the page shows. */
  section: SettingsSection;
  /** Switch to another section and record it in the query. */
  setSection: (next: SettingsSection) => void;
}

/** The active section of the settings page, deep-linkable through the query. */
export function useSettingsSection(): SettingsSectionState {
  // Deep-linkable section: ?section=llm opens the model config directly (the
  // composer's manage-models entry jumps here); unknown values degrade to the
  // appearance default. Section changes rewrite the query (replace) so a
  // refresh keeps the active section.
  const [searchParams, setSearchParams] = useSearchParams();
  const querySection = searchParams.get('section') as SettingsSection | null;
  const [section, setSectionState] = useState<SettingsSection>(
    querySection && NAV_SECTIONS.has(querySection) ? querySection : 'appearance'
  );
  // The query syncs while mounted, not only at mount: a navigate() to this
  // same route re-renders without remounting, so an in-page deep link would
  // otherwise never land. An illegal value is scrubbed from the query instead
  // of lingering next to a default section.
  useEffect(() => {
    if (querySection && NAV_SECTIONS.has(querySection)) {
      setSectionState(querySection);
    } else if (querySection !== null) {
      setSearchParams({}, { replace: true });
    }
  }, [querySection, setSearchParams]);
  const setSection = (next: SettingsSection) => {
    setSectionState(next);
    setSearchParams(next === 'appearance' ? {} : { section: next }, { replace: true });
  };
  return { section, setSection };
}
