/**
 * @file projectProgressCard
 * @description Unit tests for ProjectProgressCard's progress semantics: the
 * progress pills were converted from aria-selected buttons to role="radio"
 * inside a role="radiogroup" (a11y batch), so each pill must expose
 * aria-checked for the current progress and keep raising onProgressChange.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import type { Project } from '@/api/types';
import { ProjectProgressCard } from '@/pages/sources/ProjectProgressCard';

function makeProject(progress: Project['progress']): Project {
  return {
    id: 'p1',
    name: 'voyager',
    description: 'demo project',
    language: 'TypeScript',
    stars: 1,
    category_id: null,
    progress,
    source: 'github',
    status: 'ready',
    added_ts: 0,
    updated_ts: 0,
  };
}

function renderCard(progress: Project['progress'], onProgressChange = () => {}) {
  return render(
    <ProjectProgressCard
      project={makeProject(progress)}
      scribeName="voyager"
      noteGenerating={false}
      onProgressChange={onProgressChange}
      onGenerateNote={() => {}}
    />
  );
}

describe('ProjectProgressCard progress radios', () => {
  beforeAll(() => {
    initI18n();
  });

  it('exposes the progress pills as role="radio" with aria-checked', () => {
    renderCard('learning');

    const group = screen.getByRole('radiogroup', { name: '学习进度' });
    const radios = within(group).getAllByRole('radio');
    expect(radios).toHaveLength(4);
    expect(screen.getByRole('radio', { name: '学习中' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: '待开始' })).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByRole('radio', { name: '已掌握' })).toHaveAttribute('aria-checked', 'false');
  });

  it('raises onProgressChange with the picked progress value', () => {
    const onProgressChange = vi.fn();
    renderCard('none', onProgressChange);

    fireEvent.click(screen.getByRole('radio', { name: '已掌握' }));

    expect(onProgressChange).toHaveBeenCalledWith('mastered');
  });

  it('selects the neighbor progress on arrow keys and moves focus', () => {
    const onProgressChange = vi.fn();
    const { rerender } = renderCard('learning', onProgressChange);

    fireEvent.keyDown(screen.getByRole('radiogroup'), { key: 'ArrowRight' });
    expect(onProgressChange).toHaveBeenLastCalledWith('learned');
    expect(screen.getByRole('radio', { name: '已学习' })).toHaveFocus();

    rerender(
      <ProjectProgressCard
        project={makeProject('learned')}
        scribeName="voyager"
        noteGenerating={false}
        onProgressChange={onProgressChange}
        onGenerateNote={() => {}}
      />
    );
    fireEvent.keyDown(screen.getByRole('radiogroup'), { key: 'ArrowLeft' });
    expect(onProgressChange).toHaveBeenLastCalledWith('learning');
    expect(screen.getByRole('radio', { name: '学习中' })).toHaveFocus();
  });
});
