/**
 * @file ProjectHero
 * @description Top hero card of the project detail page (avatar / title / metadata / analysis and GitHub entries).
 *
 * Responsibilities:
 * - Render the project header: avatar gradient, title, stars/language/
 *   dates metadata, and category/progress chips
 * - Host the recommended-agent analysis entry and the GitHub link
 */
import type { AgentId, Project } from '@/api/types';
import { useTranslation } from 'react-i18next';
import { abbrevCount } from '@/utils/format';
import { safeHttpUrl } from '@/utils/safeUrl';
import { formatDate } from '@/utils/date';
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';

interface ProjectHeroProps {
  project: Project;
  /** Expert recommended from learning progress (mastered -> Elio, otherwise Iris) */
  recommendedAgent: AgentId;
  noteGenerating: boolean;
  /** Starts an expert analysis (runAgent on the coordinator page) */
  onRunAgent: (agent: AgentId) => void;
}

/** Hero card: project header and primary action entries */
export function ProjectHero({
  project,
  recommendedAgent,
  noteGenerating,
  onRunAgent,
}: ProjectHeroProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={`pd-hero ${GLASS_OUTER}`}>
      <div className="pd-avatar">
        <svg viewBox="-11.5 -10.232 23 20.464" fill="none">
          <circle r="2.05" fill="#fff" />
          <g stroke="#fff" strokeWidth="1" fill="none">
            <ellipse rx="11" ry="4.2" />
            <ellipse rx="11" ry="4.2" transform="rotate(60)" />
            <ellipse rx="11" ry="4.2" transform="rotate(120)" />
          </g>
        </svg>
      </div>
      <div className="pd-hero-body">
        <h1 className="pd-title">{project.name}</h1>
        <p className="pd-desc">{project.description}</p>
        <div className="pd-meta">
          <span className="pd-meta-item">
            <svg viewBox="0 0 24 24" fill="currentColor" width={14} height={14}>
              <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
            </svg>
            <strong>{abbrevCount(project.stars)}</strong>&nbsp;stars
          </span>
          <span className="pd-meta-sep" />
          <span className="pd-meta-item">
            <strong>{project.language ?? '-'}</strong>
          </span>
          <span className="pd-meta-sep" />
          <span className="pd-meta-item">
            {t('sources:hero.addedPrefix')}
            <strong>{formatDate(project.imported_at)}</strong>
          </span>
        </div>
      </div>
      <div className="pd-hero-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={noteGenerating}
          onClick={() => void onRunAgent(recommendedAgent)}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width={14}
            height={14}
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          {recommendedAgent === 'explainer'
            ? t('sources:hero.analyzeDeep')
            : t('sources:hero.analyzeQuick')}
        </button>
        <a
          className={`btn ${GLASS_INNER}`}
          href={safeHttpUrl(project.url) ?? undefined}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('sources:hero.openGithub')}
        </a>
      </div>
    </div>
  );
}
