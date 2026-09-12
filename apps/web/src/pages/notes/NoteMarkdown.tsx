/**
 * @file NoteMarkdown
 * @description Markdown preview for notes; highlight recovery and fence handling stay in the page module so the shared renderer stays untouched.
 *
 * Responsibilities:
 * - Flatten multi-line highlight marks before rendering
 * - Enable the notes remark plugin and map highlight marks to classes
 *   plus the --notes-hl custom property
 */

import type { CSSProperties } from 'react';
import { MarkdownRenderer } from '@/components/common/MarkdownRenderer';
import { notesHlMarkProps, recoverTonedMarkup } from './noteHl';
import { flattenMultilineMarks } from './noteMarkApply';
import { NOTE_PREVIEW_REMARK } from './noteMarkRemark';

function noteMarkProps(className?: string): { className: string; style?: CSSProperties } {
  const hl = notesHlMarkProps(className);
  return {
    className: hl.className,
    style: hl.color ? { ['--notes-hl' as string]: hl.color } : undefined,
  };
}

export function NoteMarkdown({ content, className }: { content: string; className?: string }) {
  return (
    <MarkdownRenderer
      content={flattenMultilineMarks(content)}
      className={className}
      remarkPlugins={NOTE_PREVIEW_REMARK}
      recoverCodeMarkup={recoverTonedMarkup}
      markProps={noteMarkProps}
    />
  );
}
