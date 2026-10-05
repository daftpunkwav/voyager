/**
 * @file markdownImageLightbox
 * @description Behavior lock for markdown image controls: a standalone image
 * is a native button that opens the lightbox, an image inside a working link
 * stays a plain image (the anchor is its activation target), and an image
 * under a rejected link (an empty wiki target renders a bare span) keeps its
 * own lightbox button instead of becoming inert.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { initI18n } from '@/i18n';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';

function renderMarkdown(content: string) {
  return render(
    <MemoryRouter>
      <MarkdownRenderer content={content} />
    </MemoryRouter>
  );
}

describe('markdown image lightbox controls', () => {
  beforeAll(() => {
    initI18n();
  });

  it('wraps a standalone image in a button that opens the lightbox', () => {
    renderMarkdown('![chart](https://example.com/a.png)');
    fireEvent.click(screen.getByRole('button', { name: 'chart' }));
    expect(screen.getByRole('dialog', { name: 'chart' })).toBeInTheDocument();
  });

  it('falls back to the file name as the accessible name when alt is empty', () => {
    renderMarkdown('![](https://example.com/a.png)');
    expect(screen.getByRole('button', { name: 'a.png' })).toBeInTheDocument();
  });

  it('keeps an image inside a working link a plain image', () => {
    renderMarkdown('[![chart](https://example.com/a.png)](https://example.com)');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'chart' })).toBeInTheDocument();
  });

  it('keeps the lightbox button under a rejected link (empty wiki target)', () => {
    renderMarkdown('[![chart](https://example.com/a.png)](#wiki:%20)');
    expect(screen.getByRole('button', { name: 'chart' })).toBeInTheDocument();
  });
});
