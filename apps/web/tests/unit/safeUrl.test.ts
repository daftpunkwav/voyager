/**
 * @file safeUrl
 * @description Unit tests for URL safety helpers: internal path allow-list,
 * http(s)-only external URLs and image sources, attachment source rewriting,
 * and the route table.
 */

import { describe, expect, it } from 'vitest';
import { safeHttpUrl, safeImgSrc, safeInternalPath } from '@/utils/safeUrl';
import { routes } from '@/utils/routes';

describe('safeInternalPath', () => {
  it('allows same-origin relative paths and query strings', () => {
    expect(safeInternalPath('/notes?note=abc')).toBe('/notes?note=abc');
    expect(safeInternalPath('/code-graph/x')).toBe('/code-graph/x');
  });

  it('rejects protocol-relative URLs, external links, and javascript:', () => {
    expect(safeInternalPath('//evil.example/phish')).toBeNull();
    expect(safeInternalPath('https://evil.example/')).toBeNull();
    expect(safeInternalPath('javascript:alert(1)')).toBeNull();
    expect(safeInternalPath('/\\\\server\\share')).toBeNull();
    expect(safeInternalPath('/notes/../settings')).toBeNull();
    expect(safeInternalPath('/notes?note=a..b')).toBe('/notes?note=a..b');
  });
});

describe('safeHttpUrl / safeImgSrc', () => {
  it('only allows http(s) external URLs', () => {
    expect(safeHttpUrl('https://github.com/a/b')).toBe('https://github.com/a/b');
    expect(safeHttpUrl('javascript:alert(1)')).toBeUndefined();
    expect(safeHttpUrl('/local')).toBeUndefined();
  });

  it('rewrites attachment image sources to the same-origin API and rejects path traversal', () => {
    expect(safeImgSrc('attachment://nid1')).toBe('/api/notes/assets/nid1');
    expect(safeImgSrc('attachment://../etc/passwd')).toBeUndefined();
    expect(safeImgSrc('/api/notes/assets/x')).toBe('/api/notes/assets/x');
    expect(safeImgSrc('/api/../secrets')).toBeUndefined();
    expect(safeImgSrc('/api/%2e%2e/secrets')).toBeUndefined();
  });
});

describe('routes', () => {
  it('source and graph paths match the App route table', () => {
    expect(routes.sourceRepo('p1')).toBe('/sources/repo/p1');
    expect(routes.codeGraph('p1')).toBe('/code-graph/p1');
    expect(routes.note('n1', 'p1')).toContain('note=n1');
    expect(routes.sourceOf('doc', 'd1')).toBe('/sources/doc/d1');
    expect(routes.sourceOf('web', 'w1')).toBe('/sources/web/w1');
    expect(routes.sourceOf('repo', 'p1')).toBe('/sources/repo/p1');
  });
});
