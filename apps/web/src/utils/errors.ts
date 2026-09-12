/**
 * @file errors
 * @description Error-shape detection and user-facing message extraction.
 *
 * User copy follows the errorCodes.ts pattern: it resolves through the errors
 * namespace at call time.
 *
 * Responsibilities:
 * - Detect legacy API error envelopes by shape
 * - Extract user-readable messages, mapping fetch/network failures to the
 *   unified "backend unreachable" copy
 *
 * This module must not depend on UI-layer components.
 */

import { i18n } from '@/i18n';

/** Legacy API error envelope: { error: { message } }.
 *  Distinct from ApiError ({ code, message }) in api/types; runtime checks by
 *  envelope shape ('error' in err), hence the local type. */
interface LegacyErrorEnvelope {
  error: { message: string };
}

/** Unified user copy for when the backend is unreachable (empty states / fetch / capability). */
export function backendUnreachable(): string {
  return i18n.t('errors:backendUnreachable');
}

/** Check whether the value looks like an API error response. */
export function isApiError(err: unknown): err is LegacyErrorEnvelope {
  return (
    typeof err === 'object' &&
    err !== null &&
    'error' in err &&
    typeof (err as LegacyErrorEnvelope).error?.message === 'string'
  );
}

/** Extract a user-readable message from an unknown error value. */
export function extractErrorMessage(err: unknown): string {
  if (isApiError(err)) {
    return err.error.message;
  }
  if (err instanceof TypeError && /fetch|network|Failed to fetch/i.test(err.message)) {
    return backendUnreachable();
  }
  if (err instanceof Error) {
    if (/Failed to fetch|NetworkError|Load failed/i.test(err.message)) {
      return backendUnreachable();
    }
    return err.message;
  }
  return i18n.t('errors:unknownRetry');
}
