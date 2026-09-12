/**
 * @file SourceCard
 * @description Unified source-stream card: kind icon, status badge, and metadata; clicking opens the matching reader.
 *
 * Responsibilities:
 * - Render a cross-kind source summary: kind icon, status badge, tags,
 *   category, and dates
 * - Link to the matching reader route for the card's kind
 */

import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { formatDate } from '@/i18n';
import type { SourceSummary } from '@/hooks/useSources';

const KIND_META: Record<string, { icon: React.ReactNode }> = {
  repo: {
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        width={18}
        height={18}
      >
        <path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" />
        <path d="M3 7l9 4 9-4" />
      </svg>
    ),
  },
  doc: {
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        width={18}
        height={18}
      >
        <path d="M14 2H6a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V7z" />
        <path d="M14 2v5h5M9 13h6M9 17h6" />
      </svg>
    ),
  },
  web: {
    icon: (
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        width={18}
        height={18}
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18z" />
      </svg>
    ),
  },
};

const STATUS_CLS: Record<string, string> = {
  importing: 'is-busy',
  parsing: 'is-busy',
  ready: 'is-ok',
  stored: 'is-idle',
  failed: 'is-fail',
};

export function SourceCard({ item }: { item: SourceSummary }) {
  const { t } = useTranslation('sources');
  const kind = KIND_META[item.kind] ? item.kind : 'repo';
  const meta = KIND_META[kind];
  const statusKey = STATUS_CLS[item.status] ? item.status : 'ready';
  const statusCls = STATUS_CLS[statusKey];
  const href =
    item.kind === 'doc'
      ? `/sources/doc/${item.id}`
      : item.kind === 'web'
        ? `/sources/web/${item.id}`
        : `/sources/repo/${item.id}`;
  return (
    <Link
      to={href}
      className={`source-card glass-card glass-card--overview-outer source-card--${item.kind}`}
      data-testid={`source-card-${item.kind}`}
    >
      <div className="source-card__top">
        <span className={`source-card__kind source-card__kind--${item.kind}`}>{meta.icon}</span>
        <span className={`source-card__status ${statusCls}`}>
          {t(`sources:card.status.${statusKey}`)}
        </span>
      </div>
      <h3 className="source-card__title">{item.title}</h3>
      {item.subtitle && <p className="source-card__subtitle">{item.subtitle}</p>}
      <div className="source-card__foot">
        {item.category && <span className="badge">{item.category}</span>}
        {item.tags.slice(0, 3).map((t) => (
          <span key={t} className="badge badge--tag">
            {t}
          </span>
        ))}
        <span className="source-card__time">
          {formatDate(new Date((item.updated_ts || item.added_ts) * 1000))}
        </span>
      </div>
    </Link>
  );
}
