/**
 * @file ProjectRelatedPanel
 * @description Related-projects panel of the project detail page (top 5 similar edges from the graph).
 *
 * Responsibilities:
 * - Render the similarity-sorted related-project list with links
 * - Resolve names through the coordinator's project map and show the
 *   empty state
 */
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { REPO_AVATAR_GRADIENTS } from '@/utils/format';
import { routes } from '@/utils/routes';
import { GLASS_OUTER } from '@/constants/glassTokens';

/** Related-project entry (computed from useGraph edges on the coordinator page) */
export interface ProjectRelatedItem {
  id: string;
  sim: number;
}

interface ProjectRelatedPanelProps {
  related: ProjectRelatedItem[];
  /** id -> project name map (aggregated from useProjects on the coordinator page) */
  projectMap: Map<string, { name: string }>;
}

/** Related-projects tab content: similarity list (empty-state copy kept unchanged) */
export function ProjectRelatedPanel({ related, projectMap }: ProjectRelatedPanelProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={`${GLASS_OUTER}`} style={{ padding: 16 }}>
      {related.length === 0 ? (
        <p className="muted" style={{ textAlign: 'center', padding: 24 }}>
          {t('sources:related.empty')}
        </p>
      ) : (
        <div className="pd-related-list">
          {related.map((r, i) => {
            const p = projectMap.get(r.id);
            if (!p) return null;
            const [, repoName] = p.name.split('/');
            return (
              <Link key={r.id} className="pd-related-item" to={routes.sourceRepo(r.id)}>
                <div
                  className="pd-related-avatar"
                  style={{ background: REPO_AVATAR_GRADIENTS[i % REPO_AVATAR_GRADIENTS.length] }}
                >
                  {(repoName?.[0] ?? 'P').toUpperCase()}
                </div>
                <span className="pd-related-name">{p.name}</span>
                <span className="pd-related-sim">{r.sim.toFixed(2)}</span>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
