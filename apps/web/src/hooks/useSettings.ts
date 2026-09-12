/**
 * @file useSettings
 * @description Settings schema list (get_settings) for the settings page gate.
 * Appearance values go through useTheme/useLocale; llm and agent settings
 * blocks use their own client APIs and capabilities.
 */

import { useEffect } from 'react';
import { useSettingsStore } from '@/stores/settingsStore';

export function useSettings() {
  const settings = useSettingsStore((s) => s.settings);
  const isLoading = useSettingsStore((s) => s.isLoading);
  const loadSettings = useSettingsStore((s) => s.loadSettings);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  return {
    settings,
    isLoading,
    loadSettings,
  };
}
