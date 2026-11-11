/**
 * @file ProjectTable
 * @description Project list table with row selection (page-level select-all with indeterminate state), badges, and an empty state.
 *
 * Responsibilities:
 * - Render project rows with category badges, tags and progress pills
 * - Manage page-level selection with a select-all indeterminate checkbox
 * - Show the shared empty state when no projects match
 *
 * The row, the column definitions and the empty state live in ./table.
 */

import { type ChangeEvent } from 'react';
import type { Category, Project, Tag } from '@/api/types';
import { useProjectStore } from '@/stores/projectStore';
import { ProjectTableHeader } from '@/components/project/table/ProjectTableHeader';
import { ProjectTableRow } from '@/components/project/table/ProjectTableRow';
import { ProjectTableEmpty } from '@/components/project/table/ProjectTableEmpty';

interface ProjectTableProps {
  projects: Project[];
  tags: Tag[];
  categories?: Category[];
  onImportClick?: () => void;
}

export function ProjectTable({
  projects,
  tags,
  categories = [],
  onImportClick,
}: ProjectTableProps) {
  const tagMap = new Map(tags.map((tag) => [tag.id, tag.name]));

  const selectedIds = useProjectStore((s) => s.selectedIds);
  const toggleSelected = useProjectStore((s) => s.toggleSelected);
  const setSelected = useProjectStore((s) => s.setSelected);

  const pageIds = projects.map((p) => p.id);
  const selectedSet = new Set(selectedIds);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedSet.has(id));
  const someOnPageSelected = pageIds.some((id) => selectedSet.has(id)) && !allOnPageSelected;

  const handleHeaderToggle = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.checked) {
      // Select all on the current page: merge and dedupe
      const next = new Set(selectedIds);
      pageIds.forEach((id) => next.add(id));
      setSelected(Array.from(next));
    } else {
      // Deselect the current page
      const pageSet = new Set(pageIds);
      setSelected(selectedIds.filter((id) => !pageSet.has(id)));
    }
  };

  if (projects.length === 0) {
    return (
      <div id="table-wrap" data-testid="project-table">
        <ProjectTableEmpty onImportClick={onImportClick} />
      </div>
    );
  }

  return (
    <div id="table-wrap" data-testid="project-table">
      <table className="table">
        <ProjectTableHeader
          allOnPageSelected={allOnPageSelected}
          someOnPageSelected={someOnPageSelected}
          onToggle={handleHeaderToggle}
        />
        <tbody>
          {projects.map((p, i) => (
            <ProjectTableRow
              key={p.id}
              project={p}
              index={i}
              categories={categories}
              tagMap={tagMap}
              selected={selectedSet.has(p.id)}
              onToggleSelected={toggleSelected}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
