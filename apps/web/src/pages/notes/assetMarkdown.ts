/**
 * @file assetMarkdown
 * @description Markdown insert for a notes.add_asset result. The insert is
 * derived from the payload alone, so it lives outside the editor component:
 * the editor pulls in CodeMirror, which would make the mapping untestable on
 * its own.
 *
 * Responsibilities:
 * - Map an add_asset payload to the exact Markdown inserted into the editor
 *
 * This module must not depend on UI-layer components.
 */

/** add_asset payload: the backend returns the rendered markdown (or a url)
 *  for the uploaded asset; any other field is ignored. */
export interface AssetPayload {
  /** Markdown rendered by the backend; wins even when it is empty. */
  markdown?: string;
  /** Asset url, inserted as an image link with an empty alt text. */
  url?: string;
  [key: string]: unknown;
}

/** Markdown insert for an addAsset result: the returned markdown wins even
 *  when empty (matching the old ?? chain), then a url link; a null or
 *  field-less payload degrades to the legacy String(payload) alt text
 *  ('null' / '[object Object]'), byte-for-byte. */
export function assetMarkdown(payload: AssetPayload | null): string {
  if (payload?.markdown != null) return payload.markdown;
  if (payload?.url) return `![](${payload.url})`;
  if (payload === null) return '![](null)';
  return '![]([object Object])';
}
