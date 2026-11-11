/**
 * @file projectTable
 * @description Characterization coverage for the project list table: the rows
 * it renders, the page-level select-all state it owns, the row selection and
 * the navigation its row actions trigger.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import { ProjectTable } from '@/components/project/ProjectTable';
import { useProjectStore } from '@/stores/projectStore';
import type { Project } from '@/api/types';

function project(over: Partial<Project> = {}): Project {
  return {
    id: 'p1',
    name: 'hello-world',
    owner: 'octocat',
    description: 'demo repo',
    language: 'TypeScript',
    stars: 1234,
    category_id: 'cat_frontend',
    category: 'cat_frontend',
    tags: ['tag_ts'],
    progress: 'learning',
    source: 'github',
    status: 'ready',
    added_ts: 0,
    updated_ts: 0,
    ...over,
  };
}

const projects = [
  project(),
  project({
    id: 'p2',
    name: 'gitee/thing',
    owner: '',
    description: '',
    language: null,
    stars: 42,
    category_id: '',
    category: '',
    tags: [],
    progress: 'none',
  }),
];

const tags = [{ id: 'tag_ts', name: 'TypeScript' }];

/** Detail route target: proves where a row click navigates to. */
function RepoDetail() {
  const { id } = useParams();
  return <div>repo-detail:{id}</div>;
}

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  useProjectStore.setState({ selectedIds: [] });
});

function renderTable(items: Project[] = projects, onImportClick = vi.fn()) {
  return render(
    <MemoryRouter initialEntries={['/sources']}>
      <Routes>
        <Route
          path="/sources"
          element={<ProjectTable projects={items} tags={tags} onImportClick={onImportClick} />}
        />
        <Route path="/sources/repo/:id" element={<RepoDetail />} />
      </Routes>
    </MemoryRouter>
  );
}

describe('ProjectTable', () => {
  it('renders one row per project with repo, category, language, stars and tags', () => {
    renderTable();
    expect(screen.getByTestId('project-table')).toBeTruthy();
    expect(screen.getByTestId('project-row-p1')).toBeTruthy();
    expect(screen.getByTestId('project-row-p2')).toBeTruthy();
    // repo cell splits owner and name
    expect(screen.getByText('octocat')).toBeTruthy();
    expect(screen.getByText('hello-world')).toBeTruthy();
    // category badge resolves through the label map
    expect(screen.getByText('前端')).toBeTruthy();
    // language and stars
    expect(screen.getByText('TypeScript', { selector: '.lang-dot' })).toBeTruthy();
    expect(screen.getByText('★ 1234')).toBeTruthy();
    // tag name comes from the tag table, not the raw id
    expect(screen.getByText('TypeScript', { selector: '.tag' })).toBeTruthy();
  });

  it('toggles a single row selection and marks the row as selected', () => {
    renderTable();
    const row = screen.getByTestId('project-row-p1');
    expect(row.className).not.toContain('is-selected');
    fireEvent.click(screen.getByTestId('projects-row-check-p1'));
    expect(useProjectStore.getState().selectedIds).toEqual(['p1']);
    expect(screen.getByTestId('project-row-p1').className).toContain('is-selected');
    // the row itself did not navigate: the checkbox stops the click
    expect(screen.queryByText(/repo-detail:/)).toBeNull();
  });

  it('selects every project of the page through the header checkbox', () => {
    renderTable();
    fireEvent.click(screen.getByTestId('projects-select-all'));
    expect(useProjectStore.getState().selectedIds).toEqual(['p1', 'p2']);
    expect(screen.getByTestId('project-row-p1').className).toContain('is-selected');
    expect(screen.getByTestId('project-row-p2').className).toContain('is-selected');
  });

  it('opens the repo detail route when a row is clicked', () => {
    renderTable();
    fireEvent.click(screen.getByText('hello-world'));
    expect(screen.getByText('repo-detail:p1')).toBeTruthy();
  });

  it('shows the empty state with the import actions when there is no project', () => {
    const onImportClick = vi.fn();
    renderTable([], onImportClick);
    expect(screen.getByTestId('project-table')).toBeTruthy();
    expect(screen.queryByTestId('project-row-p1')).toBeNull();
    expect(screen.getByText('还没有项目入库')).toBeTruthy();
    fireEvent.click(screen.getByTestId('empty-import-stars-btn'));
    expect(onImportClick).toHaveBeenCalledTimes(1);
  });
});
