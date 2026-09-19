/**
 * @file GraphListView
 * @description List view of the graph page: per-resource avatar, meta info, relation preview, and code-graph entry.
 *
 * Presentational subcomponent extracted from GraphPage; navigation is raised
 * via callbacks (the page owns `navigate`). Row structure, classNames, and the
 * relation computation (top 3 from getSimilarNodes) match the original.
 *
 * Responsibilities:
 * - Render per-resource rows: avatar gradient, kind label, meta, and
 *   relation preview
 * - Raise selection, open-resource, and code-graph actions via callbacks
 */

import { useTranslation } from 'react-i18next';
import { getSimilarNodes } from '@/components/graph/GraphControls';
import { abbrevCount, REPO_AVATAR_GRADIENTS } from '@/utils/format';
import { KIND_LABELS } from './graphConstants';
import type { GraphData, GraphNode } from '@/api/types';

interface GraphListViewProps {
  data: GraphData;
  selectedNodeId: string | null;
  onSelectNode: (id: string) => void;
  /** Double-click on a row opens the resource detail. */
  onOpenResource: (node: GraphNode) => void;
  /** "Code graph" entry button. */
  onOpenCodeGraph: (node: GraphNode) => void;
}

export function GraphListView({
  data,
  selectedNodeId,
  onSelectNode,
  onOpenResource,
  onOpenCodeGraph,
}: GraphListViewProps) {
  const { t } = useTranslation('graph');
  return (
    <div className="graph-list-view">
      <div className="graph-list-view__head">
        <h2>{t('graph:list.title')}</h2>
        <span>{t('graph:list.total', { total: data.nodes.length })}</span>
      </div>
      {data.nodes.map((n, idx) => {
        const similar = getSimilarNodes(data, n.id).slice(0, 3);
        const isRepo = !n.kind || n.kind === 'repo';
        return (
          <button
            key={n.id}
            type="button"
            className={`graph-list-item${selectedNodeId === n.id ? ' is-selected' : ''}`}
            onClick={() => onSelectNode(n.id)}
            onDoubleClick={() => onOpenResource(n)}
          >
            <div
              className="graph-list-avatar"
              style={{
                background: REPO_AVATAR_GRADIENTS[idx % REPO_AVATAR_GRADIENTS.length],
              }}
            >
              {(n.name[0] ?? 'R').toUpperCase()}
            </div>
            <div className="graph-list-body">
              <div className="graph-list-name">{n.name}</div>
              <div className="graph-list-meta">
                <span>
                  {KIND_LABELS[n.kind ?? 'repo'] ? t(KIND_LABELS[n.kind ?? 'repo']) : null}
                </span>
                {n.category && (
                  <>
                    <span>·</span>
                    <span>{n.category}</span>
                  </>
                )}
                {isRepo && (
                  <>
                    <span>·</span>
                    <span>{abbrevCount(n.stars)} ★</span>
                  </>
                )}
                {n.tags && n.tags.length > 0 && (
                  <>
                    <span>·</span>
                    <span>{n.tags.slice(0, 3).join(' / ')}</span>
                  </>
                )}
                {similar.length > 0 && (
                  <>
                    <span>·</span>
                    <span className="graph-list-similar">
                      {t('graph:list.similar', {
                        names: similar.map((s) => s.node.name).join(t('graph:join.enum')),
                      })}
                    </span>
                  </>
                )}
              </div>
            </div>
            {isRepo && (
              <div
                className="graph-list-action"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenCodeGraph(n);
                }}
              >
                {t('graph:list.openCodeGraph')}
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
