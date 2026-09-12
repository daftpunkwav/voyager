/**
 * @file format
 * @description Small formatting helpers: number abbreviation, repo-name
 * splitting, avatar gradients and language CSS classes.
 *
 * Responsibilities:
 * - Abbreviate numbers and split owner/repo names for display
 * - Provide repo avatar gradients and language-to-CSS-class resolution
 *
 * This module must not depend on UI-layer components.
 */

/** Abbreviate numbers (e.g. 15000 -> "15k"). */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return '0';
  if (n >= 10000) return `${Math.floor(n / 1000)}k`;
  return String(n);
}

/** Split a "owner/repo" repository name. */
export function splitRepoName(name: string): { owner: string; repo: string } {
  const [owner = '', repo = ''] = name.split('/');
  return { owner, repo };
}

/** Repo avatar gradients for the project list. */
export const REPO_AVATAR_GRADIENTS = [
  'linear-gradient(135deg,#61dafb,#2196f3)',
  'linear-gradient(135deg,#42b883,#35495e)',
  'linear-gradient(135deg,#000,#404040)',
  'linear-gradient(135deg,#38bdf8,#0ea5e9)',
  'linear-gradient(135deg,#009688,#00695c)',
  'linear-gradient(135deg,#ffd43b,#306998)',
  'linear-gradient(135deg,#3178c6,#235a97)',
  'linear-gradient(135deg,#f9a03c,#e67e22)',
  'linear-gradient(135deg,#1c3c3c,#0d2626)',
  'linear-gradient(135deg,#336791,#1f3f5a)',
  'linear-gradient(135deg,#2496ed,#0db7ed)',
  'linear-gradient(135deg,#000,#444)',
] as const;

export function langCssClass(language: string | null | undefined): string {
  if (!language) return 'lang-other';
  const l = language.toLowerCase();
  if (l.includes('typescript') || l === 'ts') return 'lang-ts';
  if (l.includes('javascript') || l === 'js') return 'lang-js';
  if (l.includes('python')) return 'lang-python';
  if (l.includes('rust')) return 'lang-rust';
  if (l.includes('c++') || l.includes('cpp')) return 'lang-cpp';
  return `lang-${l.replace(/[^a-z]/g, '').slice(0, 6) || 'other'}`;
}
