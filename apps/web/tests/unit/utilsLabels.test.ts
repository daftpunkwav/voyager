/**
 * @file utilsLabels
 * @description Pins the label-mapping contract (utils/labels.ts):
 * progress/category label resolution through the overview namespace, the
 * API-first category lookup, CSS theme classification, and the persona
 * initials table.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { initI18n, i18n } from '@/i18n';
import { progressLabel, categoryLabel, categoryCssClass, AGENT_INITIALS } from '@/utils/labels';

beforeAll(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
});

describe('utils/labels progressLabel', () => {
  it('renders a dash for missing progress', () => {
    expect(progressLabel(undefined)).toBe('-');
    expect(progressLabel('')).toBe('-');
  });

  it('resolves known ids through the overview namespace', () => {
    const label = progressLabel('learning');
    expect(label).not.toBe('learning');
    expect(i18n.exists('overview:progress.learning')).toBe(true);
  });

  it('passes unknown ids through as-is', () => {
    expect(progressLabel('no_such_progress')).toBe('no_such_progress');
  });
});

describe('utils/labels categoryLabel', () => {
  const categories = [{ id: 'c1', name: '资料库分类' }];

  it('renders a dash for missing id', () => {
    expect(categoryLabel(undefined)).toBe('-');
    expect(categoryLabel(null)).toBe('-');
  });

  it('prefers the API-provided category name', () => {
    expect(categoryLabel('c1', categories)).toBe('资料库分类');
  });

  it('falls back to the legacy static key map', () => {
    const label = categoryLabel('cat_frontend');
    expect(label).not.toBe('cat_frontend');
  });

  it('passes unknown ids through when neither source knows them', () => {
    expect(categoryLabel('cat_nope')).toBe('cat_nope');
  });
});

describe('utils/labels categoryCssClass', () => {
  it('maps legacy static ids to theme classes (cat_data collapses into cat-ai)', () => {
    expect(categoryCssClass('cat_frontend')).toBe('cat-frontend');
    expect(categoryCssClass('cat_data')).toBe('cat-ai');
    expect(categoryCssClass('cat_other')).toBe('cat-other');
  });

  it('classifies by semantic keyword matching over API names', () => {
    const named = (name: string) => [{ id: 'x', name }];
    expect(categoryCssClass('x', named('前端框架'))).toBe('cat-frontend');
    expect(categoryCssClass('x', named('Backend services'))).toBe('cat-backend');
    expect(categoryCssClass('x', named('数据平台'))).toBe('cat-ai');
    expect(categoryCssClass('x', named('DevOps 工具'))).toBe('cat-devops');
    expect(categoryCssClass('x', named('移动端'))).toBe('cat-mobile');
    expect(categoryCssClass('x', named('小工具'))).toBe('cat-tools');
    expect(categoryCssClass('x', named('杂项'))).toBe('cat-other');
  });

  it('falls back to cat-other for unknown ids without a matching name', () => {
    expect(categoryCssClass('mystery')).toBe('cat-other');
    expect(categoryCssClass(undefined)).toBe('cat-other');
  });
});

describe('utils/labels AGENT_INITIALS', () => {
  it('covers the resident orchestrator and the preset personas', () => {
    expect(AGENT_INITIALS.orchestrator).toBe('L');
    expect(AGENT_INITIALS.lucien).toBe('L');
    expect(AGENT_INITIALS.recon).toBe('I');
    expect(AGENT_INITIALS.explainer).toBe('E');
    expect(AGENT_INITIALS.organizer).toBe('M');
    expect(AGENT_INITIALS.graph_guide).toBe('A');
  });
});
