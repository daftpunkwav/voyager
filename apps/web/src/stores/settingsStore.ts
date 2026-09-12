/**
 * @file settingsStore.ts
 * @description Settings store: loads the settings schema list (get_settings)
 * for gating and dynamic groups. Business values are read/written per key via
 * the dedicated hooks and capabilities (useTheme, useLocale, llm and agent
 * settings blocks), not through this store.
 *
 * Responsibilities:
 * - Load the settings schema list once (get_settings) for gating and
 *   dynamic groups
 * - Surface loading/error state with user-extracted messages
 *
 * This module must not depend on UI-layer components.
 */
import { create } from 'zustand';
import type { SettingSchemaItem } from '@/api/types';
import { getSettings } from '@/api/settings';
import { extractErrorMessage } from '@/utils/errors';

interface SettingsState {
  settings: SettingSchemaItem[] | null;
  isLoading: boolean;
  error: string | null;
  loadSettings: () => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: null,
  isLoading: false,
  error: null,

  loadSettings: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await getSettings();
      set({ settings: data, isLoading: false });
    } catch (err) {
      set({ isLoading: false, error: extractErrorMessage(err) });
    }
  },
}));
