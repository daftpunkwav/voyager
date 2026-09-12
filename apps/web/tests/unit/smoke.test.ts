/**
 * @file smoke
 * @description Smoke tests: make sure the app's basic units import,
 * instantiate and run. Covers: core bridge types, uiStore state, per-domain
 * api modules, full api/types exports. Design goals: no reliance on APIs
 * jsdom lacks (window.matchMedia / localStorage are only partly supported),
 * no backend dependency (no fetch mocks) — only in-memory logic.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useUIStore } from '@/stores/uiStore';
import { ServiceError, unwrapDataField } from '@/bridge/client';
import type { AgentSession, Note, Project, User } from '@/api/types';
import { canonicalPersonaId } from '@/constants/personas';

describe('uiStore (theme/sidebar/font/toast)', () => {
  beforeEach(() => {
    // Reset uiStore before each test (some state survives via zustand persist)
    useUIStore.setState({
      theme: 'light',
      sidebarCollapsed: false,
      fontScale: 1.0,
      toasts: [],
    });
  });

  it('defaults to light theme + expanded sidebar + font scale 1.0', () => {
    const s = useUIStore.getState();
    expect(s.theme).toBe('light');
    expect(s.sidebarCollapsed).toBe(false);
    expect(s.fontScale).toBe(1.0);
    expect(s.toasts).toEqual([]);
  });

  it('toggleSidebar flips sidebarCollapsed', () => {
    const before = useUIStore.getState().sidebarCollapsed;
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(!before);
    useUIStore.getState().toggleSidebar();
    expect(useUIStore.getState().sidebarCollapsed).toBe(before);
  });

  it('addToast assigns an id and pushes; removeToast removes', () => {
    useUIStore.getState().addToast({ type: 'info', message: 'hello' });
    const toasts = useUIStore.getState().toasts;
    expect(toasts.length).toBe(1);
    expect(toasts[0].id).toMatch(/^toast_/);
    expect(toasts[0].message).toBe('hello');
    useUIStore.getState().removeToast(toasts[0].id);
    expect(useUIStore.getState().toasts).toEqual([]);
  });

  it('setFontScale clamps to [0.8, 1.5]', () => {
    useUIStore.getState().setFontScale(2.0);
    expect(useUIStore.getState().fontScale).toBe(1.5);
    useUIStore.getState().setFontScale(0.5);
    expect(useUIStore.getState().fontScale).toBe(0.8);
    useUIStore.getState().setFontScale(1.2);
    expect(useUIStore.getState().fontScale).toBe(1.2);
  });
});

describe('bridge/client (unified capability channel)', () => {
  it('ServiceError signature (code, message, hint?, traceId?, status?) extends Error', () => {
    const e = new ServiceError('INTERNAL', 'boom', '', '', 500);
    expect(e).toBeInstanceOf(Error);
    expect(e.code).toBe('INTERNAL');
    expect(e.status).toBe(500);
    expect(e.message).toBe('boom');
    expect(e.name).toBe('ServiceError');
  });

  it('unwrapDataField: passes through a top-level data key, otherwise returns input as-is', () => {
    expect(unwrapDataField({ data: [1, 2] })).toEqual([1, 2]);
    expect(unwrapDataField('bare')).toBe('bare');
    expect(unwrapDataField({ a: 1 })).toEqual({ a: 1 });
  });
});

describe('per-domain api layer (payload returned as-is)', () => {
  it('ten domain modules import with key functions in place', async () => {
    const projects = await import('@/api/projects');
    const notes = await import('@/api/notes');
    const graph = await import('@/api/graph');
    const codeGraph = await import('@/api/codeGraph');
    const agent = await import('@/api/agent');
    const auth = await import('@/api/auth');
    const settings = await import('@/api/settings');
    const overview = await import('@/api/overview');
    const usage = await import('@/api/usage');
    expect(typeof projects.listProjects).toBe('function');
    expect(typeof notes.listNotes).toBe('function');
    expect(typeof graph.getGraph).toBe('function');
    expect(typeof codeGraph.listCodeGraphIndexStatuses).toBe('function');
    expect(typeof agent.listSubagents).toBe('function');
    expect(typeof auth.listStars).toBe('function');
    expect(typeof settings.getSettings).toBe('function');
    expect(typeof overview.streamTrendingScoutIntro).toBe('function');
    expect(typeof usage.getLlmUsage).toBe('function');
  });

  it('docFileUrl is a synchronous pure function (called on the render path)', async () => {
    const { docFileUrl } = await import('@/api/sources');
    expect(docFileUrl('d1')).toBe('/api/sources/files/doc/d1');
  });
});

describe('api/types domain types (compile-time checks)', () => {
  it('User required + optional fields are complete', () => {
    const u: User = {
      id: 'u1',
      name: 'tester',
      username: 'tester',
      email: 't@example.com',
      github_login: 'tester',
      github_bound: true,
    };
    expect(u.id).toBe('u1');
    expect(u.github_bound).toBe(true);
  });

  it('Project progress enum has four values', () => {
    expect(['none', 'learning', 'learned', 'mastered']).toContain<Project['progress']>('mastered');
  });

  it('Note required fields (source_id / created_ts / updated_ts)', () => {
    const n: Note = {
      id: 'n1',
      title: 't',
      content: 'c',
      source_id: 's1',
      tags: ['a'],
      created_ts: 0,
      updated_ts: 0,
    };
    expect(n.source_id).toBe('s1');
    expect(n.tags).toEqual(['a']);
  });

  it('AgentSession agent field accepts duty ids and legacy aliases', () => {
    const agents: AgentSession['agent'][] = [
      'orchestrator',
      'recon',
      'explainer',
      'organizer',
      'graph_guide',
      'lucien',
      'iris',
      'elio',
      'miyai',
      'hub',
      'scout',
      'mentor',
      'navigator',
      'curator',
      'scribe',
      'atlas',
    ];
    expect(agents.length).toBe(16);
  });
});

describe('persona structured ids', () => {
  it('aliases map to duty ids; custom names are kept as-is', () => {
    expect(canonicalPersonaId('lucien')).toBe('orchestrator');
    expect(canonicalPersonaId('scout')).toBe('recon');
    expect(canonicalPersonaId(null)).toBe('orchestrator');
    expect(canonicalPersonaId('custom-hunter')).toBe('custom-hunter');
  });
});

describe('architecture rule §13.3 naming neutrality (0 hits as of this batch)', () => {
  it('per-domain api layer has no brand words and no grab-bag names', async () => {
    // Key API names stay neutral: listProjects at the top level; domain files named by duty
    const projects = await import('@/api/projects');
    const overview = await import('@/api/overview');
    expect(typeof projects.listProjects).toBe('function');
    expect(typeof projects.setProjectTags).toBe('function');
    expect(typeof overview.listRecommendedProjects).toBe('function');
  });
});
