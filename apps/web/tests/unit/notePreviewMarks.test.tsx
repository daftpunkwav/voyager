/**
 * @file notePreviewMarks
 * @description Unit tests for note preview highlight marks: ==mark== parsing
 * in list items and inline code, literal == inside fences, toned/custom RGB
 * colors, and arch-diagram marks inside fences.
 */

import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { NoteMarkdown } from '@/pages/notes/NoteMarkdown';

function preview(md: string) {
  return render(
    <MemoryRouter>
      <div className="preview-content">
        <NoteMarkdown content={md} />
      </div>
    </MemoryRouter>
  );
}

describe('note preview highlight marks', () => {
  it('bold inside list items becomes mark without leaking ==', () => {
    const { container } = preview('1. ==cool:**学习与了解** 说明==');
    expect(container.textContent).not.toContain('==');
    const mark = container.querySelector('mark.notes-hl-cool');
    expect(mark).toBeTruthy();
    expect(mark?.querySelector('strong')?.textContent).toBe('学习与了解');
    expect(mark?.textContent).toContain('说明');
  });

  it('mark can wrap inline code without splitting or leaking == at backticks', () => {
    const { container } = preview('==cool:行内 `hello` 外面==');
    expect(container.textContent).not.toContain('==');
    expect(container.querySelector('mark.notes-hl-cool')).toBeTruthy();
    expect(container.querySelector('code')?.textContent).toBe('hello');
  });

  it('literal == inside code fences is preserved as-is', () => {
    const { container } = preview('```\nconst pattern = "==a=="\n```\n');
    expect(container.textContent).toContain('const pattern = "==a=="');
    expect(container.querySelector('mark')).toBeNull();
  });

  it('cyan/violet and custom RGB marks get colored', () => {
    const violet = preview('==violet:紫段==');
    expect(violet.container.querySelector('mark.notes-hl-violet')?.textContent).toBe('紫段');
    const rgb = preview('==rgb7c3aed:自定义==');
    const mark = rgb.container.querySelector('mark.notes-hl-rgb') as HTMLElement | null;
    expect(mark?.textContent).toBe('自定义');
    expect(mark?.style.getPropertyValue('--notes-hl')).toBe('#7c3aed');
  });

  it('arch-diagram marks mistakenly written inside a fence are still recognized as a layered diagram', () => {
    const md = [
      '```',
      '==rose:+-----+',
      '==rose:| 层A |',
      '==rose:+-----+',
      '==rose:| 层B |',
      '==rose:+-----+',
      '```',
    ].join('\n');
    const { container } = preview(md);
    expect(container.querySelector('.md-arch-stack')).toBeTruthy();
    expect(container.textContent).not.toContain('==rose:');
    expect(container.textContent).toContain('层A');
    expect(container.textContent).toContain('层B');
  });
});
