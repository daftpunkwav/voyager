/**
 * @file errorCodes
 * @description Display mapping for backend/frontend error codes, keyed by the
 * backend ErrorSuffix enum (single source of truth lives in the platform contracts).
 *
 * Backend codes look like `<DOMAIN>.<SUFFIX>`; this table maps each suffix to
 * a severity while the user-visible title/hint live in the `errors` namespace
 * (`<SUFFIX>.title` / `<SUFFIX>.hint`) so they follow the UI language.
 * describeError accepts both full codes and bare suffixes (local codes
 * produced by the bridge layer are bare suffixes). Any new backend
 * ErrorSuffix value must be registered here and in every locale's
 * errors.json; a unit test keeps the suffix list in sync with the backend enum.
 *
 * Responsibilities:
 * - Map error-code suffixes (backend enum plus frontend-local codes) to
 *   toast severities
 * - Describe errors as title/hint/severity resolved through the errors
 *   namespace, accepting full codes and bare suffixes
 * - Format toast text as "[CODE] Title" with caller fallbacks for unknown
 *   codes
 *
 * This module must not depend on UI-layer components.
 */

import { i18n } from '@/i18n';

export type ErrorSeverity = 'error' | 'warning' | 'info';

export interface ErrorCodeDesc {
  title: string;
  hint: string;
  severity: ErrorSeverity;
}

/** Backend ErrorSuffix values with their toast severity; copy lives in i18n. */
export const ERROR_CODES: Record<string, ErrorSeverity> = {
  UNAVAILABLE: 'error',
  QUEUE_FULL: 'warning',
  NOT_FOUND: 'error',
  AUTH_REQUIRED: 'error',
  FORBIDDEN: 'error',
  RATE_LIMITED: 'warning',
  INVALID_INPUT: 'warning',
  CONFLICT: 'warning',
  INTERNAL: 'error',

  // Frontend-local codes (produced by the bridge layer, never sent by the backend)
  NOT_IMPLEMENTED: 'warning',
  TIMEOUT: 'warning',
  UNKNOWN: 'error',
};

function fallbackDesc(): ErrorCodeDesc {
  return {
    title: i18n.t('errors:FALLBACK.title'),
    hint: i18n.t('errors:FALLBACK.hint'),
    severity: 'error',
  };
}

/** Extract the suffix part of a code: 'GRAPH.UNAVAILABLE' -> 'UNAVAILABLE'; bare suffixes pass through. */
function suffixOf(code: string): string {
  const dot = code.lastIndexOf('.');
  return dot >= 0 ? code.slice(dot + 1) : code;
}

function knownSuffix(code: string): string | null {
  const suffix = suffixOf(code);
  return suffix in ERROR_CODES ? suffix : null;
}

export function describeError(code: string): ErrorCodeDesc {
  const suffix = knownSuffix(code);
  if (!suffix) return fallbackDesc();
  return {
    title: i18n.t(`errors:${suffix}.title`),
    hint: i18n.t(`errors:${suffix}.hint`),
    severity: ERROR_CODES[suffix],
  };
}

/** Build toast text as "[CODE] Title"; unknown codes prefer the caller-provided fallback. */
export function formatErrorToast(code: string, fallbackMessage?: string): string {
  const suffix = knownSuffix(code);
  const title = suffix ? i18n.t(`errors:${suffix}.title`) : fallbackMessage || fallbackDesc().title;
  return `[${code}] ${title}`;
}
