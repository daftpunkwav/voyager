/**
 * @file GraphControls
 * @description Collapsible graph toolbar with search, view/kind/layout switches and the similarity threshold.
 *
 * Responsibilities:
 * - Bind search, view / kind / layout switches and the similarity threshold to the store
 * - Toggle the collapsible toolbar column layout
 * - Host the index status trigger (GraphIndexProgressBar)
 */
import { useTranslation } from 'react-i18next';
import { useGraphStore } from '@/stores/graphStore';
import type { GraphLayoutMode, GraphViewMode } from '@/stores/graphStore';
import { L0_EDGE_TYPES } from '@/components/graph/l0EdgeTypes';
import { GraphIndexProgressBar } from '@/components/graph/GraphIndexProgressBar';
import type { MouseEvent, ReactNode } from 'react';

interface GraphControlsProps {
  showLayout?: boolean;
  viewModes?: { id: GraphViewMode; label: string }[];
  viewMode?: GraphViewMode;
  onViewModeChange?: (mode: GraphViewMode) => void;
  /** Batch index entry slot, mounted in the top-left toolbar to avoid overlapping Atlas. */
  batchSlot?: ReactNode;
}

/** Layout ids mapped to graph:layout.* label keys; labels resolve at render. */
const LAYOUTS: { id: GraphLayoutMode; label: string }[] = [
  { id: 'force', label: 'graph:layout.force' },
  { id: 'tree', label: 'graph:layout.tree' },
  { id: 'radial', label: 'graph:layout.radial' },
];

/** Graph toolbar rendered as a single collapsible column. */
export function GraphControls({
  showLayout = true,
  viewModes,
  viewMode,
  onViewModeChange,
  batchSlot,
}: GraphControlsProps) {
  const { t } = useTranslation('graph');
  const searchQuery = useGraphStore((s) => s.searchQuery);
  const setSearchQuery = useGraphStore((s) => s.setSearchQuery);
  const minSimilarity = useGraphStore((s) => s.minSimilarity);
  const setMinSimilarity = useGraphStore((s) => s.setMinSimilarity);
  const layoutMode = useGraphStore((s) => s.layoutMode);
  const setLayoutMode = useGraphStore((s) => s.setLayoutMode);
  const edgeTypeFilter = useGraphStore((s) => s.edgeTypeFilter);
  const setEdgeTypeFilter = useGraphStore((s) => s.setEdgeTypeFilter);
  const kindsFilter = useGraphStore((s) => s.kindsFilter);
  const toggleKindFilter = useGraphStore((s) => s.toggleKindFilter);
  const leftPanelCollapsed = useGraphStore((s) => s.leftPanelCollapsed);
  const setLeftPanelCollapsed = useGraphStore((s) => s.setLeftPanelCollapsed);

  const showUniverseExtras = showLayout && viewMode !== 'list';

  /** Kind ids mapped to graph:kind.* label keys; labels resolve at render. */
  const KIND_CHIPS: { id: string; label: string }[] = [
    { id: 'repo', label: 'graph:kind.repo' },
    { id: 'doc', label: 'graph:kind.doc' },
    { id: 'web', label: 'graph:kind.web' },
  ];
  const isKindActive = (id: string) => !kindsFilter || kindsFilter.has(id);

  const handlePanelClick = (e: MouseEvent<HTMLDivElement>) => {
    if (leftPanelCollapsed) return;
    // Collapse only when the toolbar container itself is clicked; child clicks are ignored.
    if (e.target !== e.currentTarget) return;
    setLeftPanelCollapsed(true);
  };

  return (
    <div
      data-graph-toolbar
      className={`graph-toolbar graph-toolbar--column glass-card glass-card--overview-outer${
        leftPanelCollapsed ? ' is-collapsed' : ''
      }`}
      title={leftPanelCollapsed ? undefined : t('graph:toolbar.collapseHint')}
      onClick={handlePanelClick}
    >
      {leftPanelCollapsed ? (
        <button
          type="button"
          className="graph-toolbar__toggle"
          title={t('graph:toolbar.expand')}
          aria-label={t('graph:toolbar.expand')}
          aria-expanded={false}
          onClick={() => setLeftPanelCollapsed(false)}
        >
          ⟩
        </button>
      ) : (
        <>
          <label className="graph-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              placeholder={t('graph:toolbar.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </label>

          {viewModes && viewMode && onViewModeChange && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">{t('graph:toolbar.view')}</span>
              <div
                className="view-switch"
                role="group"
                aria-label={t('graph:toolbar.viewShapeAria')}
              >
                {viewModes.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={viewMode === m.id ? 'active' : undefined}
                    onClick={() => onViewModeChange(m.id)}
                  >
                    {t(m.label)}
                  </button>
                ))}
              </div>
              {/* Edge type legend appears only under the universe graph; hidden in list mode. */}
              {showUniverseExtras && (
                <div
                  className="graph-legend graph-legend--under-view"
                  aria-label={t('graph:toolbar.edgeLegendAria')}
                >
                  <button
                    type="button"
                    className={`legend-item${!edgeTypeFilter ? ' is-active' : ''}`}
                    onClick={() => setEdgeTypeFilter(null)}
                    title={t('graph:toolbar.allEdgeTypes')}
                  >
                    <span className="legend-dot" style={{ background: 'var(--text-400)' }} />
                    <span className="legend-item__text">{t('graph:edge.all')}</span>
                  </button>
                  {L0_EDGE_TYPES.map((l) => (
                    <button
                      key={l.id}
                      type="button"
                      className={`legend-item${edgeTypeFilter === l.id ? ' is-active' : ''}`}
                      onClick={() => setEdgeTypeFilter(edgeTypeFilter === l.id ? null : l.id)}
                      title={t(l.label)}
                    >
                      <span className="legend-dot" style={{ background: l.color }} />
                      <span className="legend-item__text">{t(l.label)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">{t('graph:toolbar.kind')}</span>
              <div className="view-switch" role="group" aria-label={t('graph:toolbar.kindAria')}>
                {KIND_CHIPS.map((k) => (
                  <button
                    key={k.id}
                    type="button"
                    className={isKindActive(k.id) ? 'active' : undefined}
                    title={
                      kindsFilter?.has(k.id) === false
                        ? t('graph:kindFilter.include', { name: t(k.label) })
                        : t('graph:kindFilter.exclude', { name: t(k.label) })
                    }
                    onClick={() => toggleKindFilter(k.id)}
                  >
                    {t(k.label)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">{t('graph:toolbar.layout')}</span>
              <div
                className="layout-switch"
                role="group"
                aria-label={t('graph:toolbar.layoutAria')}
              >
                {LAYOUTS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    className={layoutMode === l.id ? 'active' : undefined}
                    onClick={() => setLayoutMode(l.id)}
                  >
                    {t(l.label)}
                  </button>
                ))}
              </div>
            </div>
          )}

          {showUniverseExtras && (
            <div className="graph-toolbar__row">
              <span className="graph-toolbar__label">{t('graph:toolbar.threshold')}</span>
              <label className="graph-threshold" title={t('graph:toolbar.thresholdHint')}>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={minSimilarity}
                  onChange={(e) => setMinSimilarity(Number(e.target.value))}
                  aria-label={t('graph:toolbar.thresholdAria')}
                />
                <span className="graph-threshold__value">{minSimilarity.toFixed(2)}</span>
              </label>
            </div>
          )}

          <div className="graph-toolbar__row graph-toolbar__row--index">
            <GraphIndexProgressBar />
          </div>

          {batchSlot && (
            <div className="graph-toolbar__row graph-toolbar__row--batch">{batchSlot}</div>
          )}
        </>
      )}
    </div>
  );
}

export { getSimilarNodes } from './graphHelpers';
