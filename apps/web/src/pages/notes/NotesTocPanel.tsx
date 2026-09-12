/**
 * @file NotesTocPanel
 * @description Workspace table of contents: outline derived from the current content (updates even when unsaved); clicks let the page decide between jumping to the editor line or the preview anchor.
 *
 * Responsibilities:
 * - Render the outline tree with indent levels and slug-stable heading ids
 * - Raise jump clicks with the item and heading id to the caller
 */

import GithubSlugger from 'github-slugger';
import { useTranslation } from 'react-i18next';
import { tocHeadingLabel, type NoteTocItem } from './noteOutline';

export function TocPanel({
  items,
  onJump,
}: {
  items: NoteTocItem[];
  onJump: (item: NoteTocItem, headingId: string) => void;
}) {
  const { t } = useTranslation('notes');
  if (items.length === 0) return null;
  const slugs = new GithubSlugger();
  return (
    <nav
      className="toc-panel notes-toc-rail"
      aria-label={t('notes:toc.title')}
      data-testid="notes-toc"
    >
      <h4 className="small muted">{t('notes:toc.title')}</h4>
      <ul>
        {items.map((h, i) => {
          const label = tocHeadingLabel(h.text);
          const id = slugs.slug(label);
          return (
            <li key={`${h.line}-${i}`} style={{ paddingLeft: Math.max(0, h.level - 1) * 10 }}>
              <button
                type="button"
                data-testid="notes-toc-item"
                title={label}
                onClick={() => onJump(h, id)}
              >
                {label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
