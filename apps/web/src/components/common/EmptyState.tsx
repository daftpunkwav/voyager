/**
 * @file EmptyState
 * @description Generic empty/error state: centered icon, title, description, and a primary action.
 *
 * Icons share the same source as the sidebar NavIcons.
 *
 * Responsibilities:
 * - Render a centered icon, title, description and optional primary action
 * - Share icon definitions with the sidebar via the NavIcons set
 */

import { useTranslation } from 'react-i18next';
import { NavIcons } from '@/components/icons/NavIcons';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  /** Unified primary action for offline/load-failure states; takes precedence over action when both are provided. */
  onRetry?: () => void;
  retryLabel?: string;
}
export function EmptyState({
  title,
  description,
  action,
  icon,
  onRetry,
  retryLabel,
}: EmptyStateProps) {
  const { t } = useTranslation('common');
  const actionNode =
    action ??
    (onRetry ? (
      <button type="button" className="btn btn-primary" onClick={onRetry}>
        {retryLabel ?? t('action.retry')}
      </button>
    ) : null);

  return (
    <div className="empty-state" role="status">
      <div className="empty-state__icon" aria-hidden>
        {icon ?? EmptyStateIcons.inbox}
      </div>
      <h3 className="empty-state__title">{title}</h3>
      {description && <p className="empty-state__desc">{description}</p>}
      {actionNode && <div className="empty-state__action">{actionNode}</div>}
    </div>
  );
}

const ICON = { width: 30, height: 30 } as const;

export const EmptyStateIcons = {
  inbox: <NavIcons.notes {...ICON} />,
  team: <NavIcons.team {...ICON} />,
  graph: <NavIcons.graph {...ICON} />,
  settings: <NavIcons.settings {...ICON} />,
  activity: <NavIcons.activity {...ICON} />,
  usage: <NavIcons.usage {...ICON} />,
  health: <NavIcons.health {...ICON} />,
  library: <NavIcons.sources {...ICON} />,
  warning: (
    <svg
      viewBox="0 0 24 24"
      width={30}
      height={30}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <path d="M12 9v4" />
      <path d="M12 17h.01" />
    </svg>
  ),
} as const;
