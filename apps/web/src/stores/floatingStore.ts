/**
 * @file floatingStore.ts
 * @description Shared state for the floating chat window: open/closed and unread count.
 *
 * State is separated from the view: the FloatingChat widget keeps only visuals;
 * all cross-page/bridge open/close calls go through setOpen here so pages never
 * dig into widget internals.
 */

import { create } from 'zustand';

interface FloatingState {
  open: boolean;
  unread: number;
  setOpen: (v: boolean) => void;
}

export const useFloatingStore = create<FloatingState>((set, get) => ({
  open: false,
  unread: 0,
  setOpen: (v) => set({ open: v, unread: v ? 0 : get().unread }),
}));
