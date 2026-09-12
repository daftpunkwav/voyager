/**
 * @file NotePreview
 * @description Note preview: renders the whole document in one Markdown pass (no repeated parser churn on view-mode or font-size changes).
 *
 * Drag-selecting words/sentences offers a quick explain action via the recon
 * persona; in pure preview the full Markdown source can be toggled.
 *
 * Responsibilities:
 * - Render the whole document in a single memoized Markdown pass
 * - Offer the explain chip on drag selection and dispatch the quote to the
 *   notes explain pipeline
 * - Toggle the raw Markdown source in pure preview mode
 */

import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { personaDisplayName } from '@/constants/personas';
import { BacklinkPanel } from './NoteBacklinks';
import { NoteMarkdown } from './NoteMarkdown';
import { explainNotesQuote } from './notesView';
import { parseNotesQuote } from './noteQuote';

interface NotePreviewProps {
  title: string;
  content: string;
  noteId: string | null;
  /** Pure preview mode: the whole Markdown source can be inspected. */
  inspectable?: boolean;
  onScrollEl?: (el: HTMLDivElement | null) => void;
}

interface ExplainChip {
  quote: string;
  x: number;
  y: number;
  below: boolean;
}

const RECON_NAME = personaDisplayName('recon');

function selectionInside(root: HTMLElement): Range | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const node = sel.anchorNode;
  if (!node || !root.contains(node)) return null;
  if (sel.focusNode && !root.contains(sel.focusNode)) return null;
  return sel.getRangeAt(0);
}

function chipFromRange(range: Range): ExplainChip | null {
  const quote = parseNotesQuote(range.toString());
  if (!quote) return null;
  const rect = range.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  const below = rect.top < 52;
  return {
    quote,
    x: rect.left + rect.width / 2,
    y: below ? rect.bottom + 8 : rect.top - 8,
    below,
  };
}

export const NotePreview = memo(function NotePreview({
  title,
  content,
  noteId,
  inspectable = false,
  onScrollEl,
}: NotePreviewProps) {
  const { t } = useTranslation('notes');
  const [showSource, setShowSource] = useState(false);
  const [chip, setChip] = useState<ExplainChip | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const setRoot = useCallback(
    (el: HTMLDivElement | null) => {
      rootRef.current = el;
      onScrollEl?.(el);
    },
    [onScrollEl]
  );

  const syncChip = useCallback(() => {
    const root = rootRef.current;
    if (!root) {
      setChip(null);
      return;
    }
    const range = selectionInside(root);
    setChip(range ? chipFromRange(range) : null);
  }, []);

  useEffect(() => {
    setShowSource(false);
  }, [content]);

  useEffect(() => {
    const onPointerUp = () => {
      requestAnimationFrame(syncChip);
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setChip(null);
        return;
      }
      if (e.shiftKey || e.key.startsWith('Arrow')) requestAnimationFrame(syncChip);
    };
    const onScroll = () => setChip(null);
    document.addEventListener('mouseup', onPointerUp);
    document.addEventListener('touchend', onPointerUp, { passive: true });
    document.addEventListener('keyup', onKeyUp);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      document.removeEventListener('mouseup', onPointerUp);
      document.removeEventListener('touchend', onPointerUp);
      document.removeEventListener('keyup', onKeyUp);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [syncChip]);

  const runExplain = (quote: string) => {
    setChip(null);
    window.getSelection()?.removeAllRanges();
    explainNotesQuote(quote);
  };

  const hasBody = content.trim().length > 0;

  return (
    <div
      className={`preview-content markdown${inspectable ? ' is-inspectable' : ''}`}
      ref={setRoot}
      data-testid="note-preview"
      onContextMenu={(e) => {
        const root = rootRef.current;
        if (!root) return;
        const range = selectionInside(root);
        const next = range ? chipFromRange(range) : null;
        if (!next) return;
        e.preventDefault();
        setChip({ ...next, x: e.clientX, y: e.clientY, below: true });
      }}
    >
      {title ? <h1 className="preview-h1">{title}</h1> : null}
      {hasBody ? (
        <p className="notes-explain-hint">
          {t('notes:preview.explainHint', { name: RECON_NAME })}
          {inspectable ? (
            <>
              {' '}
              <button
                type="button"
                className="notes-preview-source-btn"
                onClick={() => setShowSource((s) => !s)}
              >
                {showSource ? t('notes:preview.showRendered') : t('notes:preview.showSource')}
              </button>
            </>
          ) : null}
        </p>
      ) : null}
      {!hasBody ? (
        <p className="muted">{t('notes:preview.noBody')}</p>
      ) : showSource ? (
        <pre className="preview-block-source" aria-label={t('notes:preview.sourceAria')}>
          {content}
        </pre>
      ) : (
        <NoteMarkdown content={content} />
      )}
      {noteId ? <BacklinkPanel noteId={noteId} /> : null}
      {chip
        ? createPortal(
            <div
              className={`notes-explain-chip${chip.below ? ' is-below' : ''}`}
              style={{ left: chip.x, top: chip.y }}
              data-testid="notes-explain-chip"
            >
              <button
                type="button"
                className="notes-explain-chip__btn"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => runExplain(chip.quote)}
              >
                {t('notes:preview.explainAction', { name: RECON_NAME })}
              </button>
            </div>,
            document.body
          )
        : null}
    </div>
  );
});
