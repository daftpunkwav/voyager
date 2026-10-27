/**
 * @file settingsSectionNav
 * @description Settings-page section wiring: the deep-linkable section state,
 * the section catalog and the panel shell that renders the active section.
 */

import { act, render, renderHook, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import type { ReactNode } from 'react';

import { initI18n } from '@/i18n';
import { NAV_GROUPS, SECTION_IDS, SECTIONS } from '@/pages/settings/sectionCatalog';
import { SettingsSectionPanel } from '@/pages/settings/SettingsSectionPanel';
import { useSettingsSection } from '@/pages/settings/useSettingsSection';

/** The query the router currently holds. */
let currentSearch = '';

/** Records the router's query so the section state can be checked against it. */
function QueryProbe() {
  currentSearch = useLocation().search;
  return null;
}

/** The section state the page holds for a given query. */
function sectionState(query: string) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={[`/settings${query}`]}>
      <QueryProbe />
      {children}
    </MemoryRouter>
  );
  return renderHook(() => useSettingsSection(), { wrapper });
}

beforeEach(() => {
  initI18n();
  currentSearch = '';
});

describe('settings page section state', () => {
  it('starts on the appearance section without a deep link', () => {
    expect(sectionState('').result.current.section).toBe('appearance');
  });

  it('opens the section a deep link names', () => {
    expect(sectionState('?section=llm').result.current.section).toBe('llm');
  });

  it('degrades an unknown section to the appearance one', () => {
    expect(sectionState('?section=bogus').result.current.section).toBe('appearance');
  });

  it('records the picked section in the query', () => {
    const { result } = sectionState('');
    act(() => result.current.setSection('memory'));
    expect(result.current.section).toBe('memory');
    expect(currentSearch).toBe('?section=memory');
  });

  it('drops the query when the picked section is the default one', () => {
    const { result } = sectionState('?section=memory');
    act(() => result.current.setSection('appearance'));
    expect(result.current.section).toBe('appearance');
    expect(currentSearch).toBe('');
  });
});

describe('settings page section catalog', () => {
  it('lists every section in exactly one navigation group', () => {
    expect(NAV_GROUPS.flatMap((group) => group.items)).toEqual(SECTION_IDS);
  });

  it('gives every section a heading and an icon', () => {
    expect(SECTION_IDS.every((id) => SECTIONS[id].titleKey && SECTIONS[id].icon)).toBe(true);
  });
});

describe('settings page section panel', () => {
  it('renders the heading the catalog names', () => {
    render(
      <SettingsSectionPanel section="mcp">
        <p>content</p>
      </SettingsSectionPanel>
    );
    expect(screen.getByRole('heading', { name: '外接 MCP' })).toBeInTheDocument();
  });
});
