/**
 * @file GraphBatchPanel
 * @description Batch-action toolbar (analyze relations / batch index / reset camera) plus the checkbox panel for bulk L1 index creation.
 *
 * Controlled subcomponent extracted from GraphPage: the open flag and the
 * selection set are owned by the page (the toolbar-height-sync hook depends on
 * `open`, and the selection is cleared by the page after a successful index).
 * This component only renders from props and fires callbacks. Button labels
 * and classNames are unchanged from the original.
 *
 * Responsibilities:
 * - Render the batch-action toolbar: L0 relation analysis, batch L1 index
 *   toggle, and camera reset (universe view only)
 * - Render the repo checkbox list for bulk L1 index selection, emitting
 *   selection changes and the index callback to the page
 */

import { useTranslation } from 'react-i18next';
import type { GraphNode } from '@/api/types';

interface GraphBatchPanelProps {
  /** Whether the panel is expanded. */
  open: boolean;
  /** "Batch index" button: toggles panel visibility. */
  onToggle: () => void;
  /** Close (X) button in the panel's top-right corner: collapses the panel only. */
  onClose: () => void;
  /** Resource-kind scope for L0 relation analysis (shown in the button title). */
  analyzeKinds: string[];
  analyzePending: boolean;
  onAnalyze: () => void;
  /** Selectable repo nodes (batch L1 indexing only applies to repos). */
  repoNodes: GraphNode[];
  selected: Set<string>;
  onSelectedChange: (next: Set<string>) => void;
  indexPending: boolean;
  onIndex: () => void;
  /** "Reset camera" is shown only in the force-graph view. */
  showCameraReset: boolean;
  onCameraReset: () => void;
}

export function GraphBatchPanel({
  open,
  onToggle,
  onClose,
  analyzeKinds,
  analyzePending,
  onAnalyze,
  repoNodes,
  selected,
  onSelectedChange,
  indexPending,
  onIndex,
  showCameraReset,
  onCameraReset,
}: GraphBatchPanelProps) {
  const { t } = useTranslation('graph');
  return (
    <>
      <div className="graph-batch-actions">
        <button
          type="button"
          className="graph-batch-btn graph-batch-btn--inline"
          disabled={analyzePending}
          onClick={onAnalyze}
          title={t('graph:batch.analyzeTitle', { kinds: analyzeKinds.join(' / ') })}
        >
          {analyzePending ? t('graph:batch.analyzing') : t('graph:batch.analyze')}
        </button>
        <button
          type="button"
          className={`graph-batch-btn graph-batch-btn--inline${open ? ' is-active' : ''}`}
          onClick={onToggle}
        >
          {t('graph:batch.index')}
        </button>
        {showCameraReset && (
          <button
            type="button"
            className="graph-batch-btn graph-batch-btn--inline"
            onClick={onCameraReset}
            title={t('graph:batch.resetCameraTitle')}
          >
            {t('graph:batch.resetCamera')}
          </button>
        )}
      </div>
      {open && (
        <div className="graph-batch-panel graph-batch-panel--inline glass-card glass-card--overview-inner">
          <div className="graph-batch-panel__head">
            <span>{t('graph:batch.panelTitle')}</span>
            <button type="button" className="graph-batch-panel__close" onClick={onClose}>
              ✕
            </button>
          </div>
          <div className="graph-batch-panel__list">
            {repoNodes.map((n) => (
              <label key={n.id} className="graph-batch-item">
                <input
                  type="checkbox"
                  checked={selected.has(n.id)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(n.id);
                    else next.delete(n.id);
                    onSelectedChange(next);
                  }}
                />
                <span>{n.name}</span>
              </label>
            ))}
          </div>
          <div className="graph-batch-panel__footer">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={selected.size === 0 || indexPending}
              onClick={onIndex}
            >
              {indexPending
                ? t('graph:batch.submitting')
                : t('graph:batch.indexSelected', { num: selected.size })}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onSelectedChange(new Set(repoNodes.map((n) => n.id)))}
            >
              {t('graph:batch.selectAll')}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onSelectedChange(new Set())}
            >
              {t('graph:batch.clear')}
            </button>
          </div>
        </div>
      )}
    </>
  );
}
