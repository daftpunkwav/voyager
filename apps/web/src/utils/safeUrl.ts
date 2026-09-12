/**
 * @file safeUrl
 * @description URL gate: internal navigation only allows same-origin relative
 * paths; external links only allow http(s).
 *
 * Responsibilities:
 * - Validate site-internal navigate targets: relative paths only, no
 *   protocol-relative URLs, traversal segments, or control characters
 * - Allow-list external hrefs to http(s) and Markdown image sources to
 *   site-relative paths, the attachment protocol, or http(s)
 *
 * This module must not depend on UI-layer components.
 */

const INTERNAL = /^\/[A-Za-z0-9\-._~:/?#[\]@!$&'()*+,;=%]*$/;

/** A `..` segment (including percent-encoded ones) counts as traversal; names like `foo..bar` pass. */
function hasDotDotSegment(raw: string): boolean {
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return true;
  }
  const norm = decoded.replace(/\\/g, '/');
  return /(^|\/)\.\.(\/|$)/.test(norm);
}

/** Site-internal path for react-router navigate. Rejects protocol-relative URLs, backslashes, javascript:, etc. */
export function safeInternalPath(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const path = raw.trim();
  if (!path.startsWith('/') || path.startsWith('//')) return null;
  if (path.includes('\\') || path.includes('://')) return null;
  // eslint-disable-next-line no-control-regex -- control characters are exactly what is rejected here; the regex must include them
  if (/[\u0000-\u001f\u007f]/.test(path)) return null;
  if (hasDotDotSegment(path)) return null;
  if (!INTERNAL.test(path)) return null;
  return path;
}

/** External href; returns undefined when invalid, callers should render plain text instead. */
export function safeHttpUrl(raw: unknown): string | undefined {
  if (typeof raw !== 'string' || !raw.trim()) return undefined;
  try {
    const url = new URL(raw.trim());
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
  } catch {
    return undefined;
  }
  return undefined;
}

/** Markdown image sources: site-relative paths / attachment protocol / http(s). */
export function safeImgSrc(raw: unknown): string | undefined {
  if (typeof raw !== 'string' || !raw) return undefined;
  if (raw.startsWith('attachment://')) {
    const id = raw.slice('attachment://'.length);
    if (!id || id.includes('..') || id.includes('/') || id.includes('\\')) return undefined;
    return `/api/notes/assets/${encodeURIComponent(id)}`;
  }
  if (raw.startsWith('/') && !raw.startsWith('//')) {
    if (raw.includes('\\') || hasDotDotSegment(raw)) return undefined;
    return raw;
  }
  return safeHttpUrl(raw);
}
