/**
 * @file SideSection
 * @description Collapsible chrome of one right-panel section: a head button
 * (chevron + title + trailing meta) and the body, which stays hidden while
 * the section is collapsed.
 *
 * Responsibilities:
 * - Own the per-section open / closed state
 * - Render the section head and the body slot
 *
 * Constraints:
 * - Presentation only: no domain data, no store access, no translation of
 *   its own (the caller passes the already localized title and meta).
 */

import { useState, type ReactNode } from 'react';

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      className={`chat-side__chev${open ? ' chat-side__chev--open' : ''}`}
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

/** Collapsible panel section: title + trailing meta + chevron; children hidden when closed. */
export function SideSection({
  title,
  meta,
  defaultOpen = true,
  children,
}: {
  title: string;
  meta?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="chat-side__section">
      <button
        type="button"
        className="chat-side__head"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Chevron open={open} />
        <span className="chat-side__title">{title}</span>
        {meta !== undefined && open ? <span className="chat-side__meta">{meta}</span> : null}
      </button>
      {open ? <div className="chat-side__body">{children}</div> : null}
    </section>
  );
}
