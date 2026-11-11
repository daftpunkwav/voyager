/**
 * @file CodeBlockLanguageBadge
 * @description Language label of a fenced snippet. The badge sits at the right
 * edge of the code-block bar and renders nothing for an unlabeled fence, so
 * the bar keeps the same layout in both cases.
 *
 * Responsibilities:
 * - Render the fence language id as the block's language badge
 *
 * Constraints:
 * - Purely presentational: the badge never changes the block's own state.
 * - An unlabeled fence must leave no badge element behind.
 */

export interface CodeBlockLanguageBadgeProps {
  /** Fence language id (already lowercased); null for unlabeled blocks. */
  lang?: string | null;
}

/** Language badge of a fenced snippet; renders nothing when unlabeled. */
export function CodeBlockLanguageBadge({ lang }: CodeBlockLanguageBadgeProps) {
  if (!lang) return null;
  return <div className="md-codeblock__lang">{lang}</div>;
}
