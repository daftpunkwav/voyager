/**
 * @file i18n/catalog
 * @description The namespace registry: which bundles exist and which one is
 * the default. Contains no copy text.
 *
 * Namespaces are added here together with resources/<locale>/<ns>.json for
 * every supported locale (the i18n:check script enforces key parity).
 *
 * Responsibilities:
 * - Register the namespace list and the namespace used by bare t() calls
 * - Anchor the per-locale bundle layout whose key parity the check script
 *   enforces
 *
 * This module must not depend on UI-layer components.
 */

export const NAMESPACES = [
  'common',
  'shell',
  'settings',
  'errors',
  'overview',
  'notes',
  'sources',
  'team',
  'graph',
  'codeGraph',
  'activity',
  'usage',
  'health',
  'chat',
  'agent',
] as const;

export type Namespace = (typeof NAMESPACES)[number];

/** Namespace used when t() is called without an explicit one. */
export const DEFAULT_NS: Namespace = 'common';
