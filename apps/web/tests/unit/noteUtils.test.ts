/**
 * @file noteUtils
 * @description Unit tests for notes settings parsing helpers: mode/layout/
 * list state defaults, clamped split ratio/font size/TOC width, the image
 * allow-list, and the sync scroll ratio.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { initI18n } from '@/i18n';
import {
  parseNotesFontSize,
  parseNotesLayout,
  parseNotesListState,
  parseNotesMode,
  parseNotesSourceId,
  parseNotesTocWidth,
  parseSplitRatio,
  parseSyncScroll,
} from '@/pages/notes/notePrefs';
import { applyLinePrefix, isPersistedNoteId, syncScrollRatio } from '@/pages/notes/noteLine';
import {
  applyNotesListing,
  groupNotesByRecency,
  noteSnippet,
  noteSourceId,
  sortNotes,
  startOfLocalDayMs,
} from '@/pages/notes/noteListing';
import { extractNoteToc, tocHeadingLabel } from '@/pages/notes/noteOutline';
import { buildNoteExplainMessage, parseNotesQuote } from '@/pages/notes/noteQuote';
import { isAllowedNoteImage } from '@/pages/notes/NoteEditor';

// Covered modules (noteListing / noteQuote) resolve notes-namespace copy via i18n
beforeAll(() => {
  initI18n();
});

describe('parseNotesMode', () => {
  it('accepts only notes-mode values, defaulting to edit', () => {
    expect(parseNotesMode('edit')).toBe('edit');
    expect(parseNotesMode('preview')).toBe('preview');
    expect(parseNotesMode('split')).toBe('split');
    expect(parseNotesMode(null)).toBe('edit');
    expect(parseNotesMode('nope')).toBe('edit');
  });
});

describe('parseNotesLayout / parseSplitRatio / parseNotesListState', () => {
  it('layout defaults to list, card must be explicit', () => {
    expect(parseNotesLayout('card')).toBe('card');
    expect(parseNotesLayout('list')).toBe('list');
    expect(parseNotesLayout(null)).toBe('list');
  });

  it('home list state defaults to active', () => {
    expect(parseNotesListState('archived')).toBe('archived');
    expect(parseNotesListState('active')).toBe('active');
    expect(parseNotesListState(null)).toBe('active');
  });

  it('split ratio is clamped to 0.32–0.72', () => {
    expect(parseSplitRatio('0.55')).toBe(0.55);
    expect(parseSplitRatio('0.1')).toBe(0.32);
    expect(parseSplitRatio('0.99')).toBe(0.72);
    expect(parseSplitRatio('nope')).toBe(0.55);
  });

  it('font size is clamped to 12–24, default 15', () => {
    expect(parseNotesFontSize(null)).toBe(15);
    expect(parseNotesFontSize('')).toBe(15);
    expect(parseNotesFontSize('18')).toBe(18);
    expect(parseNotesFontSize('8')).toBe(12);
    expect(parseNotesFontSize('40')).toBe(24);
  });

  it('TOC width is clamped to 148–480, default 188', () => {
    expect(parseNotesTocWidth(null)).toBe(188);
    expect(parseNotesTocWidth('')).toBe(188);
    expect(parseNotesTocWidth('240')).toBe(240);
    expect(parseNotesTocWidth('80')).toBe(148);
    expect(parseNotesTocWidth('900')).toBe(480);
    expect(parseNotesTocWidth('nope')).toBe(188);
  });

  it('sync scroll defaults on and only 0 turns it off', () => {
    expect(parseSyncScroll(null)).toBe(true);
    expect(parseSyncScroll('1')).toBe(true);
    expect(parseSyncScroll('0')).toBe(false);
  });

  it('invalid source_id becomes empty; valid values are truncated to 80 chars', () => {
    expect(parseNotesSourceId(null)).toBe('');
    expect(parseNotesSourceId('../etc')).toBe('');
    expect(parseNotesSourceId('a/b')).toBe('');
    expect(parseNotesSourceId('a\\b')).toBe('');
    expect(parseNotesSourceId('ok-id')).toBe('ok-id');
    expect(parseNotesSourceId(` ${'x'.repeat(90)} `)).toBe('x'.repeat(80));
  });
});

describe('isAllowedNoteImage', () => {
  it('rejects SVG, accepts png/jpeg/gif/webp', () => {
    expect(isAllowedNoteImage({ type: 'image/svg+xml', name: 'a.svg' })).toBe(false);
    expect(isAllowedNoteImage({ type: 'image/png', name: 'a.png' })).toBe(true);
    expect(isAllowedNoteImage({ type: '', name: 'shot.webp' })).toBe(true);
    expect(isAllowedNoteImage({ type: '', name: 'x.svg' })).toBe(false);
  });
});

describe('syncScrollRatio', () => {
  it('syncs by scrollable ratio and skips zero-height elements', () => {
    const from = { scrollHeight: 200, clientHeight: 100, scrollTop: 50 } as HTMLElement;
    const to = { scrollHeight: 400, clientHeight: 100, scrollTop: 0 } as HTMLElement;
    syncScrollRatio(from, to);
    expect(to.scrollTop).toBe(150);
    const stuck = { scrollHeight: 80, clientHeight: 100, scrollTop: 0 } as HTMLElement;
    const dest = { scrollHeight: 400, clientHeight: 100, scrollTop: 9 } as HTMLElement;
    syncScrollRatio(stuck, dest);
    expect(dest.scrollTop).toBe(9);
  });
});

describe('isPersistedNoteId', () => {
  it('new / empty is not a persisted note id', () => {
    expect(isPersistedNoteId('new')).toBe(false);
    expect(isPersistedNoteId(null)).toBe(false);
    expect(isPersistedNoteId('')).toBe(false);
    expect(isPersistedNoteId('n_abc')).toBe(true);
  });
});

describe('noteSourceId / noteSnippet', () => {
  it('supports both project_id and source_id', () => {
    expect(noteSourceId({ source_id: 's1' })).toBe('s1');
    expect(noteSourceId({ project_id: 'p1' })).toBe('p1');
    expect(noteSourceId({ project_id: 'p1', source_id: 's1' })).toBe('p1');
    expect(noteSourceId({})).toBe('');
  });

  it('the list snippet prefers excerpt and strips markdown markers', () => {
    expect(noteSnippet({ excerpt: '# Title summary', content: 'full body must not leak' })).toBe(
      'Title summary'
    );
    expect(noteSnippet({ content: '**bold** body' })).toBe('bold body');
    expect(noteSnippet({})).toBe('');
  });
});

describe('applyLinePrefix', () => {
  it('applies heading/quote/list prefixes and removes them on the second pass', () => {
    expect(applyLinePrefix('hello', '## ')).toBe('## hello');
    expect(applyLinePrefix('## hello', '## ')).toBe('hello');
    expect(applyLinePrefix('hello', '> ')).toBe('> hello');
    expect(applyLinePrefix('> hello', '> ')).toBe('hello');
    expect(applyLinePrefix('# old', '## ')).toBe('## old');
  });

  it('the bare - prefix does not swallow task-list markers', () => {
    expect(applyLinePrefix('- [ ] task', '- ')).toBe('- task');
    expect(applyLinePrefix('- item', '- ')).toBe('item');
    expect(applyLinePrefix('plain', '- [ ] ')).toBe('- [ ] plain');
    expect(applyLinePrefix('- [ ] plain', '- [ ] ')).toBe('plain');
  });
});

describe('sortNotes', () => {
  const a = { title: 'Beta', pinned: false, updated_ts: 100 };
  const b = { title: 'Alpha', pinned: true, updated_ts: 50 };
  const c = { title: 'Gamma', pinned: false, updated_ts: 200 };

  it('pinned always first, the rest by most recently updated', () => {
    expect(sortNotes([a, b, c], 'updated').map((n) => n.title)).toEqual(['Alpha', 'Gamma', 'Beta']);
  });

  it('pinned always first, the rest by title', () => {
    expect(sortNotes([c, a, b], 'title').map((n) => n.title)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('second-granularity updated_ts and ISO updated_at are comparable', () => {
    const older = { title: 'old', updated_ts: 1_700_000_000 };
    const newer = { title: 'new', updated_at: '2026-08-28T00:00:00.000Z' };
    expect(sortNotes([older, newer], 'updated').map((n) => n.title)).toEqual(['new', 'old']);
  });

  it('sorts by creation time with pinned still first', () => {
    const a = { title: 'a', created_ts: 30, pinned: false };
    const b = { title: 'b', created_ts: 10, pinned: true };
    const c = { title: 'c', created_ts: 20, pinned: false };
    expect(sortNotes([a, c, b], 'created').map((n) => n.title)).toEqual(['b', 'a', 'c']);
  });
});

describe('applyNotesListing / filterNotes', () => {
  const now = Date.parse('2026-08-29T12:00:00+08:00');
  const todaySec = Math.floor((startOfLocalDayMs(now) + 8 * 3_600_000) / 1000);
  // '新笔记' stays Chinese on purpose: it must keep matching the placeholder-title
  // regex (PLACEHOLDER_TITLE) that singles out agent-created drafts.
  const notes = [
    {
      title: '新笔记',
      pinned: false,
      source_id: '',
      created_ts: todaySec,
      updated_ts: todaySec,
      excerpt: 'x',
    },
    {
      title: 'Architecture',
      pinned: true,
      source_id: 'p1',
      created_ts: todaySec - 3_600,
      updated_ts: todaySec,
      excerpt: 'design draft',
    },
    {
      title: 'Old note',
      pinned: false,
      source_id: 'p1',
      created_ts: todaySec - 800_000,
      updated_ts: todaySec - 800_000,
      excerpt: 'history',
    },
  ];

  it('the draft filter picks out placeholder titles', () => {
    expect(applyNotesListing(notes, { filter: 'untitled' }).map((n) => n.title)).toEqual([
      '新笔记',
    ]);
  });

  it('unlinked / pinned / today', () => {
    expect(applyNotesListing(notes, { filter: 'unlinked' }).map((n) => n.title)).toEqual([
      '新笔记',
    ]);
    expect(applyNotesListing(notes, { filter: 'pinned' }).map((n) => n.title)).toEqual([
      'Architecture',
    ]);
    expect(applyNotesListing(notes, { filter: 'today' }, now).map((n) => n.title)).toEqual([
      'Architecture',
      '新笔记',
    ]);
  });

  it('keyword matches title or excerpt', () => {
    expect(applyNotesListing(notes, { query: 'design' }).map((n) => n.title)).toEqual([
      'Architecture',
    ]);
  });

  it('the list groups by day and empty buckets are omitted', () => {
    const buckets = groupNotesByRecency(notes, 'created', now);
    expect(buckets.map((b) => b.id)).toEqual(['today', 'older']);
    expect(buckets[0].items.map((n) => n.title)).toEqual(['新笔记', 'Architecture']);
  });
});

describe('parseNotesQuote / buildNoteExplainMessage', () => {
  it('collapses whitespace and truncates', () => {
    expect(parseNotesQuote('  a \n b  ')).toBe('a b');
    expect(parseNotesQuote('x'.repeat(600)).length).toBe(500);
    expect(parseNotesQuote('   ')).toBe('');
  });

  it('the explain message includes the title and agent name', () => {
    // zh resource copy ('快速解读' / 《》 wrapper) is asserted verbatim; the title is caller data
    const msg = buildNoteExplainMessage({
      quote: 'ReAct',
      agentName: 'Iris',
      title: 'Architecture',
    });
    expect(msg).toContain('Iris');
    expect(msg).toContain('快速解读');
    expect(msg).toContain('《Architecture》');
    expect(msg).toContain('ReAct');
  });
});

describe('extractNoteToc', () => {
  it('extracts ATX headings and skips # inside fences', () => {
    const toc = extractNoteToc('# One\nbody\n## Two\n```py\n# not a heading\n```\n### Three');
    expect(toc.map((t) => [t.level, t.text, t.line])).toEqual([
      [1, 'One', 1],
      [2, 'Two', 3],
      [3, 'Three', 7],
    ]);
  });

  it('~~~ fences and trailing hashes also match the backend', () => {
    const toc = extractNoteToc('~~~md\n# fake\n~~~\n## real heading ##\n');
    expect(toc).toEqual([{ level: 2, text: 'real heading', line: 4 }]);
  });

  it('highlight marks do not leak into TOC labels', () => {
    expect(tocHeadingLabel('==warm:Outline==')).toBe('Outline');
    expect(tocHeadingLabel('==violet:TOC==')).toBe('TOC');
    expect(tocHeadingLabel('==rgb7c3aed:Title==')).toBe('Title');
    expect(tocHeadingLabel('Plain')).toBe('Plain');
  });
});
