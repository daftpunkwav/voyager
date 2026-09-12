/**
 * @file NodeDetailPanel
 * @description Right-hand floating detail panel for the selected node, listing
 * its inbound and outbound connections grouped by edge type.
 *
 * Responsibilities:
 * - Group the selected node's inbound and outbound edges by edge type
 * - Localize edge-type names and semantic titles at render time
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { CodeGraphNode, CodeGraphEdge } from './types';
import { i18n } from '@/i18n';
import { colorForLabel } from './colors';

interface Connection {
  node: CodeGraphNode;
  edgeType: string;
  direction: 'inbound' | 'outbound';
}

interface Props {
  node: CodeGraphNode | null;
  allNodes: CodeGraphNode[];
  allEdges: CodeGraphEdge[];
  projectId: string;
  onClose: () => void;
  onNavigate: (node: CodeGraphNode) => void;
}

/** Display names for edge types (calls / defines / similar to ...). */
const EDGE_LABEL: Record<string, string> = {
  CALLS: 'calls',
  IMPORTS: 'imports',
  DEFINES: 'defines',
  DEFINES_METHOD: 'defines method',
  CONTAINS: 'contains',
  CONTAINS_FILE: 'contains file',
  CONTAINS_FOLDER: 'contains folder',
  CONTAINS_PACKAGE: 'contains package',
  HANDLES: 'handles',
  IMPLEMENTS: 'implements',
  INHERITS: 'inherits',
  USAGE: 'usage',
  USES: 'usage',
  HTTP_CALLS: 'http calls',
  ASYNC_CALLS: 'async calls',
  DATA_FLOWS: 'data flows',
  WRITES: 'writes',
  RAISES: 'raises',
  DECORATES: 'decorates',
  SIMILAR_TO: 'similar to',
  SEMANTICALLY_RELATED: 'semantically related',
  FILE_CHANGES_WITH: 'file changes with',
  HAS_BRANCH: 'has branch',
  MEMBER_OF: 'member of',
  TESTS_FILE: 'tests file',
  RELATED: 'related',
};

function formatEdgeType(raw: string): string {
  const key = raw.toUpperCase().replace(/\s+/g, '_');
  if (EDGE_LABEL[key]) return EDGE_LABEL[key];
  return raw.replace(/_/g, ' ').toLowerCase();
}

function semanticTitle(type: string, dir: 'in' | 'out'): string | null {
  // The type matching classifies engine edge types (functional); the returned
  // titles are display copy resolved from codeGraph:semantic.* keys.
  const t = type.toUpperCase();
  if (t.includes('IMPORT'))
    return i18n.t(dir === 'out' ? 'codeGraph:semantic.importOut' : 'codeGraph:semantic.importIn');
  if (t.includes('DEPEND') || t === 'USES' || t === 'USAGE')
    return i18n.t(dir === 'out' ? 'codeGraph:semantic.dependOut' : 'codeGraph:semantic.dependIn');
  if (t.includes('DEFINE'))
    return i18n.t(dir === 'out' ? 'codeGraph:semantic.defineOut' : 'codeGraph:semantic.defineIn');
  if (t === 'CALLS' || t.includes('CALL'))
    return i18n.t(dir === 'out' ? 'codeGraph:semantic.callOut' : 'codeGraph:semantic.callIn');
  if (t.includes('CONTAIN'))
    return i18n.t(dir === 'out' ? 'codeGraph:semantic.containOut' : 'codeGraph:semantic.containIn');
  if (t.includes('SIMILAR') || t.includes('SEMANTIC')) return i18n.t('codeGraph:semantic.similar');
  return null;
}

/** Right-hand detail panel: floating glass layer. */
export function NodeDetailPanel({ node, allNodes, allEdges, onClose, onNavigate }: Props) {
  const { t } = useTranslation('codeGraph');
  const connections = useMemo(() => {
    if (!node) return [] as Connection[];
    const nodeMap = new Map(allNodes.map((n) => [n.id, n]));
    const conns: Connection[] = [];
    for (const edge of allEdges) {
      if (edge.source === node.id) {
        const t = nodeMap.get(edge.target);
        if (t) {
          conns.push({
            node: t,
            edgeType: edge.type || edge.relation || 'RELATED',
            direction: 'outbound',
          });
        }
      }
      if (edge.target === node.id) {
        const s = nodeMap.get(edge.source);
        if (s) {
          conns.push({
            node: s,
            edgeType: edge.type || edge.relation || 'RELATED',
            direction: 'inbound',
          });
        }
      }
    }
    return conns;
  }, [node, allNodes, allEdges]);

  const outbound = useMemo(
    () => connections.filter((c) => c.direction === 'outbound'),
    [connections]
  );
  const inbound = useMemo(
    () => connections.filter((c) => c.direction === 'inbound'),
    [connections]
  );

  const definedKinds = useMemo(() => {
    const defs = outbound.filter((c) => /DEFINE|CONTAIN/i.test(c.edgeType));
    const byKind = new Map<string, number>();
    for (const d of defs) {
      const k = d.node.kind || d.node.label || 'Unknown';
      byKind.set(k, (byKind.get(k) || 0) + 1);
    }
    return [...byKind.entries()];
  }, [outbound]);

  if (!node) return null;

  const groupByType = (conns: Connection[]) => {
    const g = new Map<string, Connection[]>();
    for (const c of conns) {
      g.set(c.edgeType, [...(g.get(c.edgeType) ?? []), c]);
    }
    return [...g.entries()].sort((a, b) => b[1].length - a[1].length);
  };

  return (
    <aside className="code-graph-detail glass-card glass-card--overview-outer">
      <header>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="code-graph-detail__title-row">
            <span
              className="code-graph-detail__dot"
              style={{ background: node.color || colorForLabel(node.kind || node.label) }}
            />
            <h2 title={node.qualified_name || node.name}>{node.name}</h2>
          </div>
          <span className="kind">{node.kind || node.label}</span>
        </div>
        <button
          type="button"
          className="code-graph-detail__close"
          onClick={onClose}
          aria-label={t('codeGraph:action.close')}
        >
          ×
        </button>
      </header>

      <div className="code-graph-detail__body">
        {node.file_path && (
          <p className="code-graph-detail__path mono">
            {node.file_path}
            {node.start_line
              ? ` :${node.start_line}${
                  node.end_line && node.end_line !== node.start_line ? `–${node.end_line}` : ''
                }`
              : ''}
          </p>
        )}

        <div className="code-graph-detail__stats">
          <span>
            Out <strong>{outbound.length}</strong>
          </span>
          <span>
            In <strong>{inbound.length}</strong>
          </span>
          <span>
            Total <strong>{connections.length}</strong>
          </span>
        </div>

        {definedKinds.length > 0 && (
          <section className="code-graph-detail__conn">
            <h3>{t('codeGraph:detail.definedSummary')}</h3>
            <ul className="code-graph-detail__chips">
              {definedKinds.map(([k, c]) => (
                <li key={k}>
                  <span
                    className="code-graph-detail__dot"
                    style={{ background: colorForLabel(k) }}
                  />
                  {k} · {c}
                </li>
              ))}
            </ul>
          </section>
        )}

        {outbound.length > 0 && (
          <section className="code-graph-detail__conn">
            <h3>{t('codeGraph:detail.referencesOut')}</h3>
            {groupByType(outbound).map(([type, list]) => (
              <div key={`out-${type}`} className="code-graph-detail__group">
                <div className="code-graph-detail__group-label">
                  {semanticTitle(type, 'out') || formatEdgeType(type)} · {list.length}
                </div>
                <ul>
                  {list.slice(0, 40).map((c) => (
                    <li key={`o-${c.node.id}-${c.edgeType}`}>
                      <button type="button" onClick={() => onNavigate(c.node)}>
                        <span
                          className="code-graph-detail__dot"
                          style={{
                            background: c.node.color || colorForLabel(c.node.kind || c.node.label),
                          }}
                        />
                        <span className="name">{c.node.name}</span>
                        <span className="lbl">{c.node.kind || c.node.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}

        {inbound.length > 0 && (
          <section className="code-graph-detail__conn">
            <h3>{t('codeGraph:detail.referencesIn')}</h3>
            {groupByType(inbound).map(([type, list]) => (
              <div key={`in-${type}`} className="code-graph-detail__group">
                <div className="code-graph-detail__group-label">
                  {semanticTitle(type, 'in') || formatEdgeType(type)} · {list.length}
                </div>
                <ul>
                  {list.slice(0, 40).map((c) => (
                    <li key={`i-${c.node.id}-${c.edgeType}`}>
                      <button type="button" onClick={() => onNavigate(c.node)}>
                        <span
                          className="code-graph-detail__dot"
                          style={{
                            background: c.node.color || colorForLabel(c.node.kind || c.node.label),
                          }}
                        />
                        <span className="name">{c.node.name}</span>
                        <span className="lbl">{c.node.kind || c.node.label}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </section>
        )}

        {connections.length === 0 && (
          <p className="code-graph-detail__empty">{t('codeGraph:detail.emptyConnections')}</p>
        )}
      </div>
    </aside>
  );
}
