/**
 * @file PageReader
 * @description Web page reader: clipped content plus a link to the original URL; agent clips and user clips render identically.
 *
 * Responsibilities:
 * - Render clipped page content as Markdown with the original link
 * - Edit tags/title inline and remove the clip with confirmation
 * - Feed the detail id/title to the page-awareness provider
 */

import { useEffect } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useRemovePage, useSetPageMeta, useWebPage } from '@/hooks/useSources';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { safeHttpUrl } from '@/utils/safeUrl';
import { TagEditor } from './TagEditor';
import { rememberSourceDetail } from './provider';

export function PageReader() {
  const { t } = useTranslation('sources');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: page, isLoading, isError, error, refetch } = useWebPage(id);
  const removePage = useRemovePage();
  const setMeta = useSetPageMeta();
  const addToast = useUIStore((s) => s.addToast);

  // Feed the detail id / title to the page-awareness provider; the title is an empty string until it arrives (probe falls back to id)
  useEffect(() => {
    if (!id) {
      rememberSourceDetail(null);
      return;
    }
    rememberSourceDetail({ kind: 'web', id, title: page?.title ?? '' });
  }, [id, page?.title]);

  if (isLoading) {
    return (
      <div className="reader-state">
        <LoadingSpinner label={t('sources:web.loading')} />
      </div>
    );
  }
  if (isError || !page) {
    return (
      <div className="reader-state">
        <EmptyState
          title={t('sources:web.loadFailedTitle')}
          description={error instanceof Error ? error.message : t('sources:web.missing')}
          icon={EmptyStateIcons.library}
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  // Same trust boundary as every other external-data anchor in the app: the
  // scheme allowlist decides whether the original link renders at all
  const originalUrl = safeHttpUrl(page.url);

  return (
    <div className="page-reader">
      <header className="doc-reader__head">
        <Link to="/sources" className="doc-reader__back" aria-label={t('sources:backAria')}>
          ←
        </Link>
        <div className="doc-reader__meta">
          <h1>{page.title}</h1>
          <p className="muted small">
            {page.domain || t('sources:web.manual')}
            {page.meta?.chars ? t('sources:web.chars', { count: page.meta.chars }) : ''}
          </p>
          <TagEditor
            tags={page.tags ?? []}
            onChange={(tags) =>
              setMeta.mutate(
                { pageId: page.id, meta: { tags } },
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
          {originalUrl && (
            <a
              className="btn glass-card glass-card--control liquid-glass--pill liquid-glass--interactive"
              href={originalUrl}
              target="_blank"
              rel="noreferrer"
            >
              {t('sources:web.viewOriginal')}
            </a>
          )}
          <button
            type="button"
            className="icon-btn"
            aria-label={t('sources:web.deleteAria')}
            onClick={async () => {
              if (
                !(await confirmDialog({
                  message: t('sources:web.deleteConfirm', { title: page.title }),
                  danger: true,
                }))
              )
                return;
              removePage.mutate(page.id, {
                onSuccess: () => {
                  addToast({ type: 'success', message: t('sources:web.deleted') });
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
      <article className="page-reader__content">
        <MarkdownRenderer content={page.content} />
      </article>
    </div>
  );
}
