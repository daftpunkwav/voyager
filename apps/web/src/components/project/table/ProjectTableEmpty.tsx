/**
 * @file ProjectTableEmpty
 * @description Empty state of the project table: the shared empty state with
 * the two import entry points (sync starred repos, paste a repository URL).
 *
 * Responsibilities:
 * - Render the shared empty state for a page without projects
 * - Offer the two import actions
 *
 * Constraints:
 * - Presentation only: the import callback arrives through props.
 */

import { useTranslation } from 'react-i18next';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';

export function ProjectTableEmpty({ onImportClick }: { onImportClick?: () => void }) {
  const { t } = useTranslation('sources');
  return (
    <EmptyState
      title={t('sources:table.emptyTitle')}
      description={t('sources:table.emptyDesc')}
      icon={EmptyStateIcons.library}
      action={
        <>
          <button
            type="button"
            className="btn btn-primary"
            data-testid="empty-import-stars-btn"
            onClick={onImportClick}
          >
            {t('sources:table.emptySync')}
          </button>
          <button
            type="button"
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            onClick={onImportClick}
          >
            {t('sources:table.emptyPaste')}
          </button>
        </>
      }
    />
  );
}
