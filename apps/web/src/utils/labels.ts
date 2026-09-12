/**
 * @file labels
 * @description Human-readable labels for project progress and category ids,
 * plus CSS theme-class resolution for categories. User-visible labels live in
 * the overview namespace (progress.* / category.*); this module only maps ids
 * to keys. categoryCssClass keeps Chinese keyword matching on purpose — it is
 * semantic matching against API-provided names, not display copy.
 *
 * Responsibilities:
 * - Map progress ids to overview:progress.* keys, rendering unknown ids
 *   as-is
 * - Resolve category display names (API categories first, then the legacy
 *   static key map)
 * - Classify categories into CSS theme classes via semantic keyword
 *   matching, and map persona ids to avatar initials
 *
 * This module must not depend on UI-layer components.
 */

import { i18n } from '@/i18n';
import type { Category, ProjectProgress } from '@/api/types';

/** Map a progress id to its overview:progress.* label; unknown ids render as-is. */
export function progressLabel(p: ProjectProgress | string | undefined): string {
  if (!p) return '-';
  const key = `overview:progress.${p}`;
  return i18n.exists(key) ? i18n.t(key) : p;
}

/** Legacy static ids mapped to overview:category.* keys; the API-provided
 *  categories list takes precedence. */
const CATEGORY_KEY_MAP: Record<string, string> = {
  cat_frontend: 'category.frontend',
  cat_backend: 'category.backend',
  cat_ai: 'category.ai',
  cat_data: 'category.ai',
  cat_devops: 'category.devops',
  cat_mobile: 'category.other',
  cat_desktop: 'category.other',
  cat_game: 'category.other',
  cat_security: 'category.other',
  cat_tools: 'category.other',
  cat_learning: 'category.other',
  cat_other: 'category.other',
};

/** Resolve a display name by category id; prefers the API-returned categories list. */
export function categoryLabel(
  id: string | undefined | null,
  categories?: Category[] | null
): string {
  if (!id) return '-';
  if (categories?.length) {
    const hit = categories.find((c) => c.id === id);
    if (hit) return hit.name;
  }
  const key = CATEGORY_KEY_MAP[id];
  return key ? i18n.t(`overview:${key}`) : id;
}

/** Pick a CSS theme class based on the category name or id. */
export function categoryCssClass(
  id: string | undefined | null,
  categories?: Category[] | null
): string {
  if (!id) return 'cat-other';
  if (CATEGORY_KEY_MAP[id]) {
    const key = id.replace('cat_', '');
    return `cat-${key === 'data' ? 'ai' : key}`;
  }
  // Semantic keyword matching over API-provided names (Chinese + English);
  // intentionally not i18n-driven: this classifies content, it displays nothing.
  const name = (categories?.find((c) => c.id === id)?.name || '').toLowerCase();
  if (name.includes('前端') || name.includes('front')) return 'cat-frontend';
  if (name.includes('后端') || name.includes('back')) return 'cat-backend';
  if (name.includes('ai') || name.includes('ml') || name.includes('数据')) return 'cat-ai';
  if (name.includes('devops') || name.includes('运维')) return 'cat-devops';
  if (name.includes('移动') || name.includes('mobile')) return 'cat-mobile';
  if (name.includes('工具')) return 'cat-tools';
  return 'cat-other';
}

export const AGENT_INITIALS: Record<string, string> = {
  orchestrator: 'L',
  hub: 'L',
  lucien: 'L',
  recon: 'I',
  scout: 'I',
  navigator: 'I',
  iris: 'I',
  explainer: 'E',
  mentor: 'E',
  elio: 'E',
  organizer: 'M',
  curator: 'M',
  scribe: 'M',
  miyai: 'M',
  graph_guide: 'A',
  atlas: 'A',
};
