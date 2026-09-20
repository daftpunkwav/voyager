/**
 * @file GlassSelect
 * @description Glass-styled select for forms; the menu is portaled to document.body.
 *
 * Portal placement avoids clipping by toolbar overflow and card stacking contexts.
 * The menu flips above the trigger when there is not enough room below, and
 * repositions on resize/scroll; closes on outside click or Escape.
 *
 * Responsibilities:
 * - Render the trigger and portal the option menu to document.body
 * - Flip the menu above the trigger when there is not enough room below
 * - Reposition on resize / scroll and close on outside click or Escape
 */

import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

export interface GlassSelectOption {
  value: string;
  label: string;
}

interface GlassSelectProps {
  id?: string;
  value: string;
  options: GlassSelectOption[];
  onChange: (value: string) => void;
  className?: string;
  size?: 'md' | 'sm';
  disabled?: boolean;
  'aria-label'?: string;
}

interface MenuPos {
  top: number;
  left: number;
  width: number;
}

const MENU_MIN_WIDTH = 180;

/** Glass-styled dropdown for forms. The menu is portaled to body to avoid clipping by toolbars/overflow and being covered by cards. */
export function GlassSelect({
  id,
  value,
  options,
  onChange,
  className = '',
  size = 'md',
  disabled = false,
  'aria-label': ariaLabel,
}: GlassSelectProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<MenuPos | null>(null);
  // The menu flips above its trigger when the space below runs out; the scale
  // entrance must grow from the edge facing the trigger (transform-origin)
  const [flipped, setFlipped] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const listId = useId();

  const selected = options.find((o) => o.value === value) ?? options[0];

  useLayoutEffect(() => {
    if (!open || !rootRef.current) return;
    const place = () => {
      const el = rootRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const width = Math.max(r.width, MENU_MIN_WIDTH);
      let left = r.left;
      if (left + width > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - 8 - width);
      }
      const menuH = menuRef.current?.offsetHeight ?? 240;
      const below = r.bottom + 6;
      const top =
        below + menuH > window.innerHeight - 8 && r.top > menuH + 8 ? r.top - menuH - 6 : below;
      setFlipped(top !== below);
      setPos({ top, left, width });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onEsc);
    };
  }, [open]);

  const menu =
    open && pos ? (
      <ul
        ref={menuRef}
        className={`glass-select-menu glass-select-menu--portal${flipped ? ' is-flipped' : ''}`}
        id={listId}
        role="listbox"
        style={{ top: pos.top, left: pos.left, width: pos.width }}
      >
        {options.map((opt) => (
          <li key={opt.value || '__empty__'} role="presentation">
            <button
              type="button"
              role="option"
              aria-selected={opt.value === value}
              className={`glass-select-item${opt.value === value ? ' is-selected' : ''}`}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </button>
          </li>
        ))}
      </ul>
    ) : null;

  return (
    <div
      className={`glass-select glass-select--${size}${open ? ' is-open' : ''} ${className}`.trim()}
      ref={rootRef}
    >
      <button
        type="button"
        id={id}
        className="glass-select-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => {
          if (open) {
            setOpen(false);
            return;
          }
          const r = rootRef.current?.getBoundingClientRect();
          if (r) {
            setPos({
              top: r.bottom + 6,
              left: r.left,
              width: Math.max(r.width, MENU_MIN_WIDTH),
            });
          }
          setOpen(true);
        }}
      >
        <span className="glass-select-value">{selected?.label ?? '—'}</span>
        <span className="glass-select-chev" aria-hidden>
          ▾
        </span>
      </button>
      {menu ? createPortal(menu, document.body) : null}
    </div>
  );
}
