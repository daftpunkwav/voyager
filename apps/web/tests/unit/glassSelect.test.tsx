/**
 * @file glassSelect
 * @description Unit tests for GlassSelect's listbox semantics: the portaled
 * menu was converted from ul/li to div elements (a11y batch), so it must stay
 * queryable as role="listbox" with role="option" items and keep activating
 * options on click.
 */

import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GlassSelect } from '@/components/common/GlassSelect';

const OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'doc', label: 'Docs' },
  { value: 'web', label: 'Web' },
];

describe('GlassSelect listbox semantics', () => {
  it('keeps role="listbox" and role="option" queryable once the menu is open', () => {
    render(<GlassSelect value="all" options={OPTIONS} onChange={() => {}} aria-label="Kind" />);

    // The menu is portaled to document.body and only mounted after opening
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Kind' }));

    const listbox = screen.getByRole('listbox');
    expect(listbox.tagName).toBe('DIV');
    const options = within(listbox).getAllByRole('option');
    expect(options).toHaveLength(OPTIONS.length);
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('raises onChange with the picked value when an option is clicked', () => {
    const onChange = vi.fn();
    render(<GlassSelect value="all" options={OPTIONS} onChange={onChange} aria-label="Kind" />);

    fireEvent.click(screen.getByRole('button', { name: 'Kind' }));
    fireEvent.click(screen.getByRole('option', { name: 'Web' }));

    expect(onChange).toHaveBeenCalledWith('web');
  });
});
