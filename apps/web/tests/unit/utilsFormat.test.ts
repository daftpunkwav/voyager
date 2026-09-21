/**
 * @file utilsFormat
 * @description Pins the small formatting helpers (utils/format.ts):
 * number abbreviation, repo-name splitting rules, and language CSS
 * class resolution.
 */

import { describe, expect, it } from 'vitest';
import {
  abbrevCount,
  splitRepoName,
  repoDisplayParts,
  REPO_AVATAR_GRADIENTS,
  langCssClass,
} from '@/utils/format';

describe('utils/format abbrevCount', () => {
  it('renders null/undefined as 0', () => {
    expect(abbrevCount(null)).toBe('0');
    expect(abbrevCount(undefined)).toBe('0');
  });

  it('passes small numbers through', () => {
    expect(abbrevCount(0)).toBe('0');
    expect(abbrevCount(9999)).toBe('9999');
  });

  it('abbreviates at and above 10000', () => {
    expect(abbrevCount(10000)).toBe('10k');
    expect(abbrevCount(15000)).toBe('15k');
    expect(abbrevCount(999999)).toBe('999k');
  });
});

describe('utils/format repo names', () => {
  it('splits owner/repo', () => {
    expect(splitRepoName('octocat/hello')).toEqual({ owner: 'octocat', repo: 'hello' });
  });

  it('splits a bare repo name into an empty repo', () => {
    // No '/' present: the single segment lands in `owner` (array
    // destructuring default only covers missing elements).
    expect(splitRepoName('hello')).toEqual({ owner: 'hello', repo: '' });
  });

  it('repoDisplayParts prefers the owner column when present', () => {
    expect(repoDisplayParts({ owner: 'me', name: 'repo' })).toEqual({ owner: 'me', repo: 'repo' });
  });

  it('repoDisplayParts falls back to splitting a legacy full name', () => {
    expect(repoDisplayParts({ owner: null, name: 'octocat/hello' })).toEqual({
      owner: 'octocat',
      repo: 'hello',
    });
  });

  it('repoDisplayParts keeps the bare name when no owner exists', () => {
    expect(repoDisplayParts({ owner: '', name: 'hello' })).toEqual({ owner: '', repo: 'hello' });
  });
});

describe('utils/format langCssClass', () => {
  it('maps known languages to fixed classes (case-insensitive)', () => {
    expect(langCssClass('TypeScript')).toBe('lang-ts');
    expect(langCssClass('ts')).toBe('lang-ts');
    expect(langCssClass('JavaScript')).toBe('lang-js');
    expect(langCssClass('js')).toBe('lang-js');
    expect(langCssClass('Python')).toBe('lang-python');
    expect(langCssClass('Rust')).toBe('lang-rust');
    expect(langCssClass('C++')).toBe('lang-cpp');
    expect(langCssClass('cpp')).toBe('lang-cpp');
  });

  it('falls back to a sanitized slug, then lang-other', () => {
    expect(langCssClass('Go')).toBe('lang-go');
    expect(langCssClass('C#')).toBe('lang-c');
    expect(langCssClass('!!!')).toBe('lang-other');
  });

  it('maps missing language to lang-other', () => {
    expect(langCssClass(null)).toBe('lang-other');
    expect(langCssClass('')).toBe('lang-other');
  });
});

describe('utils/format avatar gradients', () => {
  it('ships a non-empty gradient table', () => {
    expect(REPO_AVATAR_GRADIENTS.length).toBeGreaterThan(0);
    for (const g of REPO_AVATAR_GRADIENTS) {
      expect(g).toMatch(/^linear-gradient/);
    }
  });
});
