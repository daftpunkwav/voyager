/**
 * @file NotFound.tsx
 * @description Unknown-route page.
 *
 * Renders an explicit not-found state instead of silently falling back to the
 * overview, so users never mistake a bad link for a successful navigation.
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { routes } from '@/utils/routes';

export function NotFound() {
  const { t } = useTranslation('shell');
  return (
    <div className="page-scaffold">
      <div className="page-scaffold__state">
        <EmptyState
          title={t('notFound.title')}
          description={t('notFound.desc')}
          icon={EmptyStateIcons.inbox}
          action={
            <Link to={routes.overview} className="btn btn-primary">
              {t('notFound.action')}
            </Link>
          }
        />
      </div>
    </div>
  );
}
