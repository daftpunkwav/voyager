/**
 * @file notesAssetMarkdown
 * @description Pins the Markdown insert derived from a notes.add_asset
 * payload: the returned markdown wins (even when it is empty), a url
 * becomes an image link with an empty alt text, and a payload without
 * either field degrades to the legacy String(payload) alt text
 * ('null' / '[object Object]').
 */

import { describe, expect, it } from 'vitest';
import { assetMarkdown } from '@/pages/notes/assetMarkdown';

describe('assetMarkdown', () => {
  it('inserts the markdown returned by the backend', () => {
    expect(assetMarkdown({ markdown: '![x](u)' })).toBe('![x](u)');
  });

  it('the markdown wins over a url carried by the same payload', () => {
    expect(assetMarkdown({ markdown: '![x](u)', url: 'https://example.test/a.png' })).toBe(
      '![x](u)'
    );
  });

  it('an empty markdown is inserted as-is (it still wins over the url)', () => {
    expect(assetMarkdown({ markdown: '', url: 'https://example.test/a.png' })).toBe('');
  });

  it('a payload without markdown falls back to the url link', () => {
    expect(assetMarkdown({ url: 'https://example.test/a.png' })).toBe(
      '![](https://example.test/a.png)'
    );
  });

  it('a null payload degrades to the legacy null alt text', () => {
    expect(assetMarkdown(null)).toBe('![](null)');
  });

  it('a payload without the known fields degrades to the legacy object alt text', () => {
    expect(assetMarkdown({})).toBe('![]([object Object])');
    expect(assetMarkdown({ other: 1 })).toBe('![]([object Object])');
  });
});
