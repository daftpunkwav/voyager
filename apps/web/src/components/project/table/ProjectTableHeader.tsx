/**
 * @file ProjectTableHeader
 * @description Column definitions of the project table: the select-all
 * checkbox column plus the repo, category, language, stars, progress, tags
 * and actions columns.
 *
 * Responsibilities:
 * - Render the table head with one cell per column
 * - Render the page-level select-all checkbox and its indeterminate state
 *
 * Constraints:
 * - Presentation only: the page selection state arrives through props and
 *   the toggle is reported back to the table.
 */

import { type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';

export function ProjectTableHeader({
  allOnPageSelected,
  someOnPageSelected,
  onToggle,
}: {
  allOnPageSelected: boolean;
  someOnPageSelected: boolean;
  onToggle: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  const { t } = useTranslation('sources');
  return (
    <thead>
      <tr>
        <th className="col-check">
          <span className="th-checkbox">
            <input
              type="checkbox"
              className="checkbox"
              aria-label={t('sources:table.selectAllAria')}
              data-testid="projects-select-all"
              checked={allOnPageSelected}
              ref={(el) => {
                if (el) el.indeterminate = someOnPageSelected;
              }}
              onChange={onToggle}
            />
          </span>
        </th>
        <th>{t('sources:table.col.repo')}</th>
        <th>{t('sources:table.col.category')}</th>
        <th>{t('sources:table.col.language')}</th>
        <th>{t('sources:table.col.stars')}</th>
        <th>{t('sources:table.col.progress')}</th>
        <th>{t('sources:table.col.tags')}</th>
        <th className="col-actions">{t('sources:table.col.actions')}</th>
      </tr>
    </thead>
  );
}
