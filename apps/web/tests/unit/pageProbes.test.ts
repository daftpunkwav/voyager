/**
 * @file pageProbes
 * @description Phase-09 unit tests: page-probe route resolution
 * (resolvePageProbe by prefix, no more equality dictionary) and per-page
 * provider summary quality (counts/title/selected; null when not ready —
 * never lies).
 */

import { beforeEach, describe, expect, it } from 'vitest';

import { initI18n } from '@/i18n';
import { resolvePageName, resolvePageProbe } from '@/shell/pageProbes';
import { chatProvider } from '@/pages/chat/provider';
import { notesProvider, rememberNotesListCount } from '@/pages/notes/provider';
import { teamProvider, rememberTeamSnapshot, patchTeamSnapshot } from '@/components/team/provider';
import { sourceDetailProvider, rememberSourceDetail } from '@/pages/sources/provider';
import { activityProvider, rememberActivityFeedCount } from '@/pages/activity/provider';
import { useChatStore } from '@/stores/chatStore';
import { useNoteStore } from '@/stores/noteStore';

beforeEach(() => {
  // The notes provider summary goes through i18n (notes ns); init once for the test env, zh-CN assertions stay.
  initI18n();
  // Per-page module caches are cross-test module state: reset before each case.
  rememberNotesListCount(null);
  rememberTeamSnapshot(null);
  rememberSourceDetail(null);
  rememberActivityFeedCount(null);
  useChatStore.setState({ messages: [] });
  useNoteStore.setState({ editingNoteId: null, editorTitle: '', editorContent: '' });
});

describe('resolvePageProbe route resolution', () => {
  it('resolves domain pages and prefix paths to the right probe', () => {
    expect(resolvePageProbe('/')?.page).toBe('chat');
    expect(resolvePageProbe('/chat')?.page).toBe('chat');
    expect(resolvePageProbe('/chat/abc')?.page).toBe('chat');
    expect(resolvePageProbe('/notes')?.page).toBe('notes');
    expect(resolvePageProbe('/notes/')?.page).toBe('notes');
    // Per spec: detail routes land on sources
    expect(resolvePageProbe('/sources/repo/abc')?.page).toBe('sources');
    expect(resolvePageProbe('/sources/doc/abc')?.page).toBe('sources');
    expect(resolvePageProbe('/graph')?.page).toBe('graph');
    expect(resolvePageProbe('/graph/sub')?.page).toBe('graph');
    expect(resolvePageProbe('/code-graph')?.page).toBe('graph');
    expect(resolvePageProbe('/code-graph/proj-1')?.page).toBe('graph');
    expect(resolvePageProbe('/team')?.page).toBe('team');
    expect(resolvePageProbe('/activity')?.page).toBe('activity');
  });

  it('settings / usage / health / overview register no provider (no reporting)', () => {
    expect(resolvePageName('/settings')).toBeNull();
    expect(resolvePageName('/usage')).toBeNull();
    expect(resolvePageName('/system/health')).toBeNull();
    expect(resolvePageName('/overview')).toBeNull();
    expect(resolvePageProbe('/settings')).toBeNull();
  });
});

describe('notes provider summary quality', () => {
  it('after the list cache is written the summary has count and the title in book quotes, counts.notes is right, no body text', () => {
    rememberNotesListCount(36);
    useNoteStore.setState({
      editingNoteId: 'n-1',
      editorTitle: 'langgraph notes',
      editorContent: 'This body text must never leak into the summary.',
    });
    const out = notesProvider.report();
    expect(out).not.toBeNull();
    expect(out?.summary).toContain('36 条笔记');
    expect(out?.summary).toContain('《langgraph notes》');
    expect(out?.counts).toMatchObject({ notes: 36 });
    expect(out?.selected).toBe('n-1');
    // editorContent must not leak into the summary
    expect(out?.summary).not.toContain('must never leak');
  });

  it('reports no zero-count lie when the list never arrived (cache null)', () => {
    const out = notesProvider.report();
    expect(out).not.toBeNull();
    expect(out?.summary).not.toContain('0 条笔记');
    expect(out?.counts).toBeUndefined();
  });

  it('an empty list (0 notes) is a real state and is reported as-is', () => {
    rememberNotesListCount(0);
    const out = notesProvider.report();
    expect(out?.summary).toContain('0 条笔记');
    expect(out?.counts).toMatchObject({ notes: 0 });
  });
});

describe('team provider summary quality', () => {
  it('returns null before any snapshot (no zero-persona report)', () => {
    expect(teamProvider.report()).toBeNull();
  });

  it('reports persona/built/running counts once the snapshot lands', () => {
    rememberTeamSnapshot({ personas: 5, definitions: 2, running: 1 });
    const out = teamProvider.report();
    expect(out?.summary).toBe('团队 · 5 个人格 · 2 个自建 · 1 个运行中');
    expect(out?.counts).toMatchObject({ personas: 5, definitions: 2, running: 1 });
  });

  it('rememberTeamSnapshot(null) clears the fields; a single patch does not commit right away', () => {
    rememberTeamSnapshot({ personas: 5, definitions: 2, running: 1 });
    rememberTeamSnapshot(null);
    patchTeamSnapshot({ personas: 1 });
    expect(teamProvider.report()).toBeNull();
  });
});

describe('sources provider summary quality', () => {
  it('detail page: falls back to id before the title arrives, uses the title after; selected is the id', () => {
    rememberSourceDetail({ kind: 'repo', id: 'abc-123', title: '' });
    let out = sourceDetailProvider.report();
    expect(out?.summary).toBe('资源详情 · 仓库 · abc-123');
    expect(out?.selected).toBe('abc-123');

    rememberSourceDetail({ kind: 'repo', id: 'abc-123', title: 'voyager/backend' });
    out = sourceDetailProvider.report();
    expect(out?.summary).toBe('资源详情 · 仓库 · voyager/backend');
  });

  it('the detail summary never carries README/body-length text', () => {
    rememberSourceDetail({
      kind: 'doc',
      id: 'd-1',
      title: 'a very long document title'.repeat(10),
    });
    const out = sourceDetailProvider.report();
    expect((out?.summary ?? '').length).toBeLessThan(80);
  });
});

describe('chat / activity provider', () => {
  it('chat: reports even at 0 messages (an empty chat is a real state)', () => {
    const out = chatProvider.report();
    expect(out?.summary).toBe('对话 · 0 条消息');
    expect(out?.counts).toMatchObject({ messages: 0 });
  });

  it('chat: reports by message count', () => {
    useChatStore.setState({
      messages: [
        { seq: 1, role: 'user', content: 'a' },
        { seq: 2, role: 'agent', content: 'b' },
      ],
    });
    expect(chatProvider.report()?.summary).toBe('对话 · 2 条消息');
  });

  it('activity: null before load; reports the count after fetch', () => {
    expect(activityProvider.report()).toBeNull();
    rememberActivityFeedCount(7);
    expect(activityProvider.report()?.summary).toBe('活动 · 7 条');
    expect(activityProvider.report()?.counts).toMatchObject({ events: 7 });
  });
});
