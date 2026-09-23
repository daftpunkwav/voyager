/**
 * @file floatingLayers
 * @description Behavior tests for the shared floating-layer mechanisms:
 * ModalOverlay's Escape routing (topmost modal only, preventDefault yields),
 * the press-AND-release scrim rule, the exit-animation reopen recovery
 * (useLeaving), Popover's lazy render prop, and the imperative confirm's
 * supersede contract (an unanswered request settles as cancelled).
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { act, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { Popover } from '@/components/common/Popover';
import { confirmDialog, useUIStore } from '@/stores/uiStore';

/** Dispatch a real keydown (so the component sees e.defaultPrevented honestly),
 *  wrapped in act() so onClose's state updates flush before assertions */
function pressEscape(prevent = false) {
  act(() => {
    const ev = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    if (prevent) ev.preventDefault();
    window.dispatchEvent(ev);
  });
}

function OverlayHost({ onClose }: { onClose: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <ModalOverlay
      open={open}
      onClose={() => {
        setOpen(false);
        onClose();
      }}
    >
      <div role="dialog">body</div>
    </ModalOverlay>
  );
}

describe('ModalOverlay Escape routing', () => {
  it('only the topmost of two stacked modals closes on Escape', () => {
    const closeBase = vi.fn();
    const closeTop = vi.fn();
    function Stacked() {
      const [baseOpen, setBaseOpen] = useState(true);
      const [topOpen, setTopOpen] = useState(true);
      return (
        <>
          <ModalOverlay
            open={baseOpen}
            onClose={() => {
              setBaseOpen(false);
              closeBase();
            }}
          />
          <ModalOverlay
            open={topOpen}
            onClose={() => {
              setTopOpen(false);
              closeTop();
            }}
          />
        </>
      );
    }
    render(<Stacked />);
    expect(document.querySelectorAll('.modal-overlay').length).toBe(2);

    pressEscape();
    expect(closeTop).toHaveBeenCalledTimes(1);
    expect(closeBase).not.toHaveBeenCalled();
    // The closed top overlay stays mounted through its exit animation
    // (useLeaving): count only the live (non-leaving) overlays.
    expect(document.querySelectorAll('.modal-overlay:not(.is-leaving)').length).toBe(1);

    pressEscape();
    expect(closeBase).toHaveBeenCalledTimes(1);
    expect(document.querySelectorAll('.modal-overlay:not(.is-leaving)').length).toBe(0);
  });

  it('an Escape already handled by an inner consumer (preventDefault) closes nothing', () => {
    const onClose = vi.fn();
    render(<OverlayHost onClose={onClose} />);
    pressEscape(true);
    expect(onClose).not.toHaveBeenCalled();
    expect(document.querySelector('.modal-overlay')).not.toBeNull();
    pressEscape();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('the scrim closes only on press AND release on the scrim itself', () => {
    const onClose = vi.fn();
    render(<OverlayHost onClose={onClose} />);
    const overlay = document.querySelector('.modal-overlay') as HTMLElement;

    // A text selection starting on the dialog and ending on the scrim: no close
    fireEvent.mouseDown(screen.getByRole('dialog'));
    fireEvent.mouseUp(overlay);
    expect(onClose).not.toHaveBeenCalled();

    // Press and release both on the scrim: closes
    fireEvent.mouseDown(overlay);
    fireEvent.mouseUp(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe('exit-animation lifecycle (useLeaving)', () => {
  it('re-opening during the exit window clears is-leaving instead of sticking', () => {
    function Host() {
      const [open, setOpen] = useState(true);
      return (
        <>
          <button type="button" onClick={() => setOpen((v) => !v)}>
            toggle
          </button>
          <ModalOverlay open={open} onClose={() => setOpen(false)}>
            <div role="dialog">body</div>
          </ModalOverlay>
        </>
      );
    }
    render(<Host />);
    fireEvent.click(screen.getByText('toggle')); // close: the exit window starts
    expect((document.querySelector('.modal-overlay') as HTMLElement).className).toContain(
      'is-leaving'
    );
    fireEvent.click(screen.getByText('toggle')); // reopen within the exit window
    const reopened = document.querySelector('.modal-overlay') as HTMLElement;
    expect(reopened).not.toBeNull();
    expect(reopened.className).not.toContain('is-leaving');
  });
});

describe('Popover lazy render prop', () => {
  it('only invokes a function child while visible, never while closed', () => {
    const renderChildren = vi.fn(() => <p>panel</p>);
    function Host() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen((v) => !v)}>
            toggle
          </button>
          <Popover open={open} onClose={() => setOpen(false)} anchorRef={{ current: null }}>
            {renderChildren}
          </Popover>
        </>
      );
    }
    render(<Host />);
    expect(renderChildren).not.toHaveBeenCalled(); // closed: never evaluated
    fireEvent.click(screen.getByText('toggle'));
    expect(screen.getByText('panel')).toBeTruthy();
    expect(renderChildren).toHaveBeenCalledTimes(1);
  });
});

describe('confirmDialog supersede', () => {
  it('a newer request settles the unanswered one as cancelled and answers on its own', async () => {
    const first = confirmDialog({ message: 'first' });
    const second = confirmDialog({ message: 'second' });
    await expect(first).resolves.toBe(false); // superseded: never left hanging
    useUIStore.getState().resolveConfirm(true);
    await expect(second).resolves.toBe(true);
    expect(useUIStore.getState().confirmRequest).toBeNull();
  });
});
