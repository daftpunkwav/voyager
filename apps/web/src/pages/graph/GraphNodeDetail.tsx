/**
 * @file GraphNodeDetail
 * @description Right-hand node detail panel: header, overview (doc/web vs repo variants), and similar-resource pagination.
 *
 * Extracted from GraphPage. Similar-node computation (getSimilarNodes) and
 * pagination state are colocated here; changing the selected node resets the
 * page number (matching the original page-level effect). Navigation is raised
 * via callbacks. Labels, classNames, and interactions are unchanged.
 *
 * Responsibilities:
 * - Render the node header and the doc/web vs. repo overview variants
 * - Compute and paginate similar resources (page reset on node change)
 * - Raise navigation (select, open resource, open code graph) via
 *   callbacks
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getSimilarNodes } from '@/components/graph/GraphControls';
import { REPO_AVATAR_GRADIENTS, splitRepoName } from '@/utils/format';
import { safeHttpUrl } from '@/utils/safeUrl';
// Glass-level tokens (the legacy OVERVIEW_OUTER_GLASS / OVERVIEW_INNER_GLASS tokens were unified into these)
import { GLASS_INNER, GLASS_OUTER } from '@/constants/glassTokens';
import { KIND_LABELS, SIMILAR_PREVIEW_COUNT } from './graphConstants';
import type { GraphData, GraphNode } from '@/api/types';

interface GraphNodeDetailProps {
  node: GraphNode;
  /** Currently filtered graph data (used for similar-node computation). */
  data: GraphData;
  /** Header close (X): clears the selection. */
  onClose: () => void;
  onSelectNode: (id: string) => void;
  /** doc/web "open resource" action. */
  onOpenResource: (node: GraphNode) => void;
  /** repo "open code graph" action. */
  onOpenCodeGraph: (node: GraphNode) => void;
  /** repo "project detail" action. */
  onOpenRepo: (node: GraphNode) => void;
}

export function GraphNodeDetail({
  node,
  data,
  onClose,
  onSelectNode,
  onOpenResource,
  onOpenCodeGraph,
  onOpenRepo,
}: GraphNodeDetailProps) {
  const { t } = useTranslation('graph');
  const [similarPage, setSimilarPage] = useState(0);

  // Reset the similar list to its first page when the selected node changes
  useEffect(() => {
    setSimilarPage(0);
  }, [node.id]);

  const selectedRepo = splitRepoName(node.name);
  const selectedGithubUrl =
    selectedRepo?.owner && selectedRepo.repo
      ? safeHttpUrl(`https://github.com/${selectedRepo.owner}/${selectedRepo.repo}`)
      : undefined;

  const similarNodes = getSimilarNodes(data, node.id);
  const similarPageCount = Math.max(1, Math.ceil(similarNodes.length / SIMILAR_PREVIEW_COUNT));
  const clampedSimilarPage = Math.min(similarPage, similarPageCount - 1);
  const visibleSimilarNodes = similarNodes.slice(
    clampedSimilarPage * SIMILAR_PREVIEW_COUNT,
    (clampedSimilarPage + 1) * SIMILAR_PREVIEW_COUNT
  );

  return (
    <div className={`node-detail ${GLASS_OUTER}`}>
      <div className="node-detail-head">
        <div className="node-avatar" style={{ background: REPO_AVATAR_GRADIENTS[0] }}>
          {(selectedRepo?.repo[0] ?? node.name[0] ?? 'R').toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="node-meta-name" title={node.name}>
            {selectedRepo?.repo || node.name}
          </div>
          {node.kind && node.kind !== 'repo' && (
            <div className="node-meta-kind">
              {KIND_LABELS[node.kind] ? t(KIND_LABELS[node.kind]) : null}
            </div>
          )}
        </div>
        <button
          type="button"
          className="node-detail-close"
          title={t('graph:action.close')}
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <div className="node-detail-body">
        {node.kind === 'doc' || node.kind === 'web' ? (
          <>
            <div className="node-detail-section">
              <div className="detail-label">{t('graph:detail.overview')}</div>
              <div className="detail-row">
                <span className="muted">{t('graph:detail.type')}</span>
                <strong>{KIND_LABELS[node.kind] ? t(KIND_LABELS[node.kind]) : null}</strong>
              </div>
              <div className="detail-row">
                <span className="muted">{t('graph:detail.category')}</span>
                <strong>{node.category || '—'}</strong>
              </div>
              <div className="detail-row">
                <span className="muted">{t('graph:detail.tags')}</span>
                <strong>
                  {node.tags && node.tags.length > 0 ? node.tags.join(t('graph:join.enum')) : '—'}
                </strong>
              </div>
            </div>
            <div className="detail-actions">
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => onOpenResource(node)}
              >
                {t('graph:detail.openResource')}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="node-detail-section">
              <div className="detail-label">{t('graph:detail.overview')}</div>
              <div className="detail-row">
                <span className="muted">{t('graph:detail.owner')}</span>
                <strong className="detail-owner">{selectedRepo?.owner || '—'}</strong>
              </div>
              <div className="detail-row">
                <span className="muted">GitHub</span>
                {selectedGithubUrl ? (
                  <a
                    className="detail-github-link"
                    href={selectedGithubUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={selectedGithubUrl}
                  >
                    {`${selectedRepo?.owner}/${selectedRepo?.repo}`}
                  </a>
                ) : (
                  <span className="muted">—</span>
                )}
              </div>
            </div>
            <div className="detail-actions">
              <button
                type="button"
                className="btn btn-primary btn-block"
                onClick={() => onOpenCodeGraph(node)}
              >
                {t('graph:detail.openCodeGraph')}
              </button>
              <button
                type="button"
                className="btn btn--secondary btn-block"
                onClick={() => onOpenRepo(node)}
              >
                {t('graph:detail.projectDetail')}
              </button>
            </div>
          </>
        )}
        {similarNodes.length > 0 && (
          <div className="node-detail-section node-detail-section--similar">
            <div className="detail-label">{t('graph:detail.similar')}</div>
            <div className="similar-list">
              {visibleSimilarNodes.map(({ node: similarNode, similarity }) => {
                const { owner, repo } = splitRepoName(similarNode.name);
                const githubUrl =
                  owner && repo ? safeHttpUrl(`https://github.com/${owner}/${repo}`) : undefined;
                return (
                  <div key={similarNode.id} className={`similar-item ${GLASS_INNER}`}>
                    <button
                      type="button"
                      className="similar-item__main"
                      onClick={() => onSelectNode(similarNode.id)}
                      title={similarNode.name}
                    >
                      <span className="similar-name">{repo || similarNode.name}</span>
                      <span className="similar-score">{similarity.toFixed(2)}</span>
                    </button>
                    <div className="similar-item__meta">
                      <span className="similar-owner">
                        {KIND_LABELS[similarNode.kind ?? 'repo']
                          ? t(KIND_LABELS[similarNode.kind ?? 'repo'])
                          : null}
                      </span>
                      {githubUrl ? (
                        <a
                          className="similar-github"
                          href={githubUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          title={t('graph:detail.openOnGithub', { owner, repo })}
                          onClick={(e) => e.stopPropagation()}
                        >
                          GitHub ↗
                        </a>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
            {similarPageCount > 1 && (
              <div
                className="similar-pager"
                role="navigation"
                aria-label={t('graph:detail.similarPagerAria')}
              >
                <button
                  type="button"
                  className="similar-pager__btn"
                  disabled={clampedSimilarPage <= 0}
                  onClick={() => setSimilarPage((p) => Math.max(0, p - 1))}
                  title={t('graph:detail.prevPage')}
                >
                  ‹
                </button>
                <span className="similar-pager__meta">
                  {clampedSimilarPage + 1} / {similarPageCount}
                </span>
                <button
                  type="button"
                  className="similar-pager__btn"
                  disabled={clampedSimilarPage >= similarPageCount - 1}
                  onClick={() => setSimilarPage((p) => Math.min(similarPageCount - 1, p + 1))}
                  title={t('graph:detail.nextPage')}
                >
                  ›
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
