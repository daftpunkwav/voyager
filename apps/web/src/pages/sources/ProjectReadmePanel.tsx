/**
 * @file ProjectReadmePanel
 * @description README panel of the project detail page (toolbar plus Markdown body).
 *
 * Font-size state stays on the coordinator page so it survives tab switches.
 *
 * Responsibilities:
 * - Render the README Markdown with font-size controls, refresh, and copy
 * - Show loading / fetching / error / backend-hint states for the readme
 *   query
 */
import type { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { GLASS_INNER } from '@/constants/glassTokens';

interface ProjectReadmePanelProps {
  /** Body text to render (query result, falling back to the project's own readme) */
  readmeText: string;
  readmeLoading: boolean;
  readmeFetching: boolean;
  readmeError: boolean;
  /** Backend hint for an empty README (readmeData?.message) */
  readmeMessage: string | undefined;
  fontSize: number;
  /** Font-size adjustment (setFontSize from the coordinator page, passed through as-is) */
  onFontSizeChange: Dispatch<SetStateAction<number>>;
  /** Refresh (refetchReadme on the coordinator page) */
  onRefresh: () => void;
  /** Copies the full text (async; invoked with void inside the child) */
  onCopy: () => Promise<void>;
}

/** README tab content: font-size controls / refresh / copy plus the Markdown body */
export function ProjectReadmePanel({
  readmeText,
  readmeLoading,
  readmeFetching,
  readmeError,
  readmeMessage,
  fontSize,
  onFontSizeChange,
  onRefresh,
  onCopy,
}: ProjectReadmePanelProps) {
  const { t } = useTranslation('sources');
  return (
    <article className="pd-readme">
      <div className="pd-readme-toolbar">
        <div className="left">
          <span>README.md</span>
        </div>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: 'var(--text-500)' }}>
          {t('sources:readme.fontSize')}
        </span>
        <div className="font-ctrl">
          <button
            type="button"
            aria-label={t('sources:readme.fontSmaller')}
            onClick={() => onFontSizeChange((f) => Math.max(11, f - 1))}
          >
            −
          </button>
          <span className="font-display" title={`${fontSize}px`}>
            {fontSize}
          </span>
          <button
            type="button"
            aria-label={t('sources:readme.fontLarger')}
            onClick={() => onFontSizeChange((f) => Math.min(20, f + 1))}
          >
            +
          </button>
        </div>
        <button
          type="button"
          className={`btn btn-sm ${GLASS_INNER}`}
          style={{ height: 28, marginLeft: 4 }}
          disabled={readmeLoading || readmeFetching}
          onClick={() => void onRefresh()}
        >
          {readmeFetching ? t('sources:refreshing') : t('sources:readme.refresh')}
        </button>
        <button
          type="button"
          className={`btn btn-sm ${GLASS_INNER}`}
          style={{ height: 28, marginLeft: 4 }}
          disabled={!readmeText}
          onClick={() => void onCopy()}
        >
          {t('sources:readme.copyAll')}
        </button>
      </div>
      <div className="pd-readme-body markdown" data-testid="readme-content" style={{ fontSize }}>
        {readmeLoading ? (
          <LoadingSpinner />
        ) : readmeText ? (
          <MarkdownRenderer content={readmeText} />
        ) : (
          <div className="pd-readme-empty">
            <p style={{ color: 'var(--text-400)', margin: '0 0 8px' }}>
              {readmeError
                ? t('sources:readme.loadFailed')
                : readmeMessage || t('sources:readme.empty')}
            </p>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => void onRefresh()}
            >
              {t('sources:readme.retry')}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
