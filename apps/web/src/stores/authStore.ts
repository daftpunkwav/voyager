/**
 * @file authStore.ts
 * @description Local learner store — no login/registration; the user is the
 * local single-user stub (api/auth.me).
 */
import { create } from 'zustand';
import type { User } from '@/api/types';

interface LocalUserState {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  setUser: (user: User | null) => void;
  clearError: () => void;
}

export const useAuthStore = create<LocalUserState>((set) => ({
  user: null,
  isLoading: false,
  error: null,

  setUser: (user) => set({ user }),
  clearError: () => set({ error: null }),
}));
