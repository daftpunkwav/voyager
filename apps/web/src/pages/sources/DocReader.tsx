/**
 * @file DocReader
 * @description Document reader with dual views: PDF original layout (pdf.js pagination) and extracted text (by section).
 *
 * Users read the original layout while agents read the extracted text.
 * EPUB / DOCX / TXT / MD have no original-layout rendering and show sectioned
 * text directly. Parsing shows progress; failures report the reason.
 *
 * Responsibilities:
 * - Switch between the PDF original layout (pdf.js pagination with a
 *   persisted scale) and the extracted-text section view
 * - Live-refresh the document while parsing via SSE events; edit meta and
 *   tags inline, delete with confirmation
 * - Feed the detail id/title to the page-awareness provider
 */

import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  useDocument,
  useDocSection,
  useDocumentEvents,
  useRemoveDocument,
  useSetDocumentMeta,
} from '@/hooks/useSources';
import { docFileUrl } from '@/api/sources';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { TagEditor } from './TagEditor';
import { rememberSourceDetail } from './provider';
import { STORAGE, migrateKey } from '@/brand';

migrateKey(STORAGE.pdfScale, STORAGE.legacy.pdfScale);

export function DocReader() {
  const { t } = useTranslation('sources');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: doc, isLoading, isError, error, refetch } = useDocument(id);
  useDocumentEvents(id);
  const removeDoc = useRemoveDocument();
  const setMeta = useSetDocumentMeta();
  const addToast = useUIStore((s) => s.addToast);

  // Feed the detail id / title to the page-awareness provider; the title is an empty string until it arrives (probe falls back to id)
  useEffect(() => {
    if (!id) {
      rememberSourceDetail(null);
      return;
    }
    rememberSourceDetail({ kind: 'doc', id, title: doc?.title ?? '' });
  }, [id, doc?.title]);
  const [view, setView] = useState<'original' | 'text'>('original');
  const [sectionNo, setSectionNo] = useState(1);

  const isPdf = doc?.ext === '.pdf';
  const parseable = doc?.status === 'ready';
  const stored = doc?.status === 'stored';

  useEffect(() => {
    if (doc && !isPdf) setView('text');
  }, [doc, isPdf]);

  // Reset the section number when switching documents: changing the param on the
  // same route does not remount, and a stale sectionNo would report "section not found" on the new document
  useEffect(() => {
    setSectionNo(1);
  }, [id]);

  if (isLoading) {
    return (
      <div className="reader-state">
        <LoadingSpinner label={t('sources:doc.loading')} />
      </div>
    );
  }
  if (isError || !doc) {
    return (
      <div className="reader-state">
        <EmptyState
          title={t('sources:doc.loadFailedTitle')}
          description={error instanceof Error ? error.message : t('sources:doc.loadFailedDesc')}
          icon={EmptyStateIcons.library}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  return (
    <div className="doc-reader">
      <header className="doc-reader__head">
        <Link to="/sources" className="doc-reader__back" aria-label={t('sources:backAria')}>
          ←
        </Link>
        <div className="doc-reader__meta">
          <h1>{doc.title}</h1>
          <p className="muted small">
            {doc.filename} ·{' '}
            {doc.total_sections > 0
              ? t('sources:doc.sectionsCount', { count: doc.total_sections })
              : doc.ext}
            {doc.status === 'parsing' && t('sources:doc.parsingBadge')}
          </p>
          <TagEditor
            tags={doc.tags ?? []}
            onChange={(tags) =>
              setMeta.mutate(
                { docId: doc.id, meta: { tags } },
                {
                  onError: (e) =>
                    addToast({
                      type: 'error',
                      message: e instanceof Error ? e.message : t('sources:tagSaveFailed'),
                    }),
                }
              )
            }
          />
        </div>
        <div className="doc-reader__actions">
          {parseable && (
            <div className="doc-reader__views" role="tablist">
              {isPdf && (
                <button
                  type="button"
                  role="tab"
                  aria-selected={view === 'original'}
                  className={`kind-tab ${view === 'original' ? 'is-active' : ''}`}
                  onClick={() => setView('original')}
                >
                  {t('sources:doc.tabOriginal')}
                </button>
              )}
              <button
                type="button"
                role="tab"
                aria-selected={view === 'text'}
                className={`kind-tab ${view === 'text' ? 'is-active' : ''}`}
                onClick={() => setView('text')}
              >
                {t('sources:doc.tabText')}
              </button>
            </div>
          )}
          <a
            className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
            href={docFileUrl(doc.id)}
            target="_blank"
            rel="noreferrer"
          >
            {t('sources:doc.openFile')}
          </a>
          <button
            type="button"
            className="icon-btn"
            aria-label={t('sources:doc.deleteAria')}
            onClick={async () => {
              if (
                !(await confirmDialog({
                  message: t('sources:doc.deleteConfirm', { title: doc.title }),
                  danger: true,
                }))
              )
                return;
              removeDoc.mutate(doc.id, {
                onSuccess: () => {
                  addToast({ type: 'success', message: t('sources:doc.deleted') });
                  navigate('/sources');
                },
                onError: (e) =>
                  addToast({
                    type: 'error',
                    message: e instanceof Error ? e.message : t('sources:deleteFailed'),
                  }),
              });
            }}
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              width={16}
              height={16}
            >
              <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
            </svg>
          </button>
        </div>
      </header>

      {doc.status === 'failed' && (
        <div className="doc-reader__failed" role="alert">
          {t('sources:doc.parseFailedPrefix')}
          {doc.error || t('sources:doc.unknownReason')}
        </div>
      )}
      {stored && <div className="doc-reader__stored">{t('sources:doc.storedHint')}</div>}
      {doc.status === 'parsing' && (
        <div className="reader-state">
          <LoadingSpinner label={t('sources:doc.parsingWait')} />
        </div>
      )}

      {parseable && view === 'original' && isPdf && (
        <PdfPane docId={doc.id} fileUrl={docFileUrl(doc.id)} />
      )}
      {parseable && (view === 'text' || !isPdf) && (
        <div className="doc-reader__text">
          <aside className="doc-reader__outline">
            <h2 className="small muted">{t('sources:doc.outline')}</h2>
            <ul>
              {doc.sections.map((s) => (
                <li key={s.section_no}>
                  <button
                    type="button"
                    className={`doc-reader__outline-item ${s.section_no === sectionNo ? 'is-active' : ''}`}
                    onClick={() => setSectionNo(s.section_no)}
                  >
                    {s.title || t('sources:doc.sectionFallback', { n: s.section_no })}
                  </button>
                </li>
              ))}
            </ul>
          </aside>
          <SectionPane
            docId={doc.id}
            sectionNo={sectionNo}
            onNav={(delta) =>
              setSectionNo((n) => Math.min(doc.total_sections, Math.max(1, n + delta)))
            }
          />
        </div>
      )}
    </div>
  );
}

function SectionPane({
  docId,
  sectionNo,
  onNav,
}: {
  docId: string;
  sectionNo: number;
  onNav: (delta: number) => void;
}) {
  const { t } = useTranslation('sources');
  const { data: section, isLoading } = useDocSection(docId, sectionNo);
  if (isLoading)
    return (
      <div className="doc-reader__content">
        <LoadingSpinner />
      </div>
    );
  if (!section)
    return <div className="doc-reader__content muted">{t('sources:doc.sectionMissing')}</div>;
  return (
    <div className="doc-reader__content">
      {section.title && <h2>{section.title}</h2>}
      <p className="muted small">
        {t('sources:doc.sectionPos', { no: section.section_no, total: section.total_sections })}
        {section.page_end > 0 &&
          t('sources:doc.sectionPages', { start: section.page_start, end: section.page_end })}
      </p>
      <MarkdownRenderer content={section.text} />
      <div className="doc-reader__pager">
        <button
          type="button"
          className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
          disabled={sectionNo <= 1}
          onClick={() => onNav(-1)}
        >
          {t('sources:doc.prevSection')}
        </button>
        <button
          type="button"
          className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
          disabled={sectionNo >= section.total_sections}
          onClick={() => onNav(1)}
        >
          {t('sources:doc.nextSection')}
        </button>
      </div>
    </div>
  );
}

const PDFJS_SCALE_KEY = STORAGE.pdfScale;

/** pdf.js original-layout paginated view (canvas rendering; cmaps are served from public/pdfjs, required for CJK text). */
function PdfPane({ docId, fileUrl }: { docId: string; fileUrl: string }) {
  const { t } = useTranslation('sources');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pageNum, setPageNum] = useState(1);
  const [total, setTotal] = useState(0);
  const [failed, setFailed] = useState('');
  const [scale, setScale] = useState(() => {
    // Guarded parse: a dirty legacy value must not poison the scale — NaN
    // would propagate through min/max and write "NaN" back to storage
    const raw = localStorage.getItem(PDFJS_SCALE_KEY);
    const n = raw !== null ? Number(raw) : NaN;
    return Number.isFinite(n) && n >= 0.5 && n <= 3 ? n : 1.2;
  });

  const docRef = useRef<import('pdfjs-dist').PDFDocumentProxy | null>(null);
  const taskRef = useRef<import('pdfjs-dist').PDFDocumentLoadingTask | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import('pdfjs-dist');
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          'pdfjs-dist/build/pdf.worker.min.mjs',
          import.meta.url
        ).toString();
        const task = pdfjs.getDocument({
          url: fileUrl,
          cMapUrl: '/pdfjs/cmaps/',
          cMapPacked: true,
          standardFontDataUrl: '/pdfjs/standard_fonts/',
        });
        taskRef.current = task;
        const pdf = await task.promise;
        if (cancelled) {
          void task.destroy();
          return;
        }
        docRef.current = pdf;
        setTotal(pdf.numPages);
      } catch (err) {
        if (!cancelled) setFailed(err instanceof Error ? err.message : t('sources:doc.pdfFailed'));
      }
    })();
    return () => {
      cancelled = true;
      void taskRef.current?.destroy();
      taskRef.current = null;
      docRef.current = null;
    };
  }, [fileUrl, t]);

  useEffect(() => {
    let renderTask: import('pdfjs-dist').RenderTask | null = null;
    const render = async () => {
      const pdf = docRef.current;
      const canvas = canvasRef.current;
      if (!pdf || !canvas || pageNum < 1 || pageNum > total) return;
      const page = await pdf.getPage(pageNum);
      const viewport = page.getViewport({ scale: scale * window.devicePixelRatio });
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.width = `${viewport.width / window.devicePixelRatio}px`;
      canvas.style.height = `${viewport.height / window.devicePixelRatio}px`;
      renderTask = page.render({ canvas, canvasContext: ctx, viewport });
      try {
        await renderTask.promise;
      } catch (err) {
        if (err instanceof Error && !err.message.includes('cancelled')) throw err;
      } finally {
        page.cleanup();
      }
    };
    void render();
    return () => {
      renderTask?.cancel();
    };
  }, [pageNum, total, scale, docId]);

  const changeScale = (delta: number) => {
    setScale((s) => {
      const next = Math.min(3, Math.max(0.5, s + delta));
      localStorage.setItem(PDFJS_SCALE_KEY, String(next));
      return next;
    });
  };

  if (failed) {
    return (
      <div className="reader-state">
        <EmptyState
          title={t('sources:doc.pdfFailed')}
          description={failed}
          icon={EmptyStateIcons.library}
        />
      </div>
    );
  }
  return (
    <div className="pdf-pane">
      <div className="pdf-pane__toolbar">
        <button
          type="button"
          className="page-btn"
          disabled={pageNum <= 1}
          onClick={() => setPageNum((n) => n - 1)}
          aria-label={t('sources:prevPage')}
        >
          ‹
        </button>
        <span className="pdf-pane__page">
          {pageNum} / {total || '…'}
        </span>
        <button
          type="button"
          className="page-btn"
          disabled={pageNum >= total}
          onClick={() => setPageNum((n) => n + 1)}
          aria-label={t('sources:nextPage')}
        >
          ›
        </button>
        <span className="pdf-pane__sep" />
        <button
          type="button"
          className="page-btn"
          onClick={() => changeScale(-0.2)}
          aria-label={t('sources:doc.zoomOut')}
        >
          −
        </button>
        <button
          type="button"
          className="page-btn"
          onClick={() => changeScale(0.2)}
          aria-label={t('sources:doc.zoomIn')}
        >
          +
        </button>
      </div>
      <div className="pdf-pane__viewport">
        <canvas ref={canvasRef} />
        {total === 0 && <LoadingSpinner label={t('sources:doc.pdfRendering')} />}
      </div>
    </div>
  );
}
