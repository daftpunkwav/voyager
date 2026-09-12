/**
 * @file DisplaySettingsMenu
 * @description Contrast and brightness settings panel for the code graph.
 *
 * Slider values stack on top of the automatic density compensation;
 * 1.00x means "follow the adaptive baseline".
 *
 * Responsibilities:
 * - Render clamped contrast / brightness sliders over the adaptive density baseline
 * - Push changes upward through onChange; close on outside click or Escape
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DEFAULT_DISPLAY_SETTINGS, DISPLAY_LIMITS, type DisplaySettings } from './density';

interface DisplaySettingsMenuProps {
  settings: DisplaySettings;
  onChange: (next: DisplaySettings) => void;
}

interface SliderRowProps {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

function SliderRow({ label, hint, value, min, max, onChange }: SliderRowProps) {
  const { t } = useTranslation('codeGraph');
  return (
    <label className="code-graph-display-menu__slider">
      <div className="code-graph-display-menu__slider-head">
        <span className="code-graph-display-menu__slider-label">{label}</span>
        <span className="code-graph-display-menu__slider-value">{value.toFixed(2)}×</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={0.05}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={t('codeGraph:display.sliderAria', { label, hint })}
      />
      <p className="code-graph-display-menu__hint">{hint}</p>
    </label>
  );
}

export function DisplaySettingsMenu({ settings, onChange }: DisplaySettingsMenuProps) {
  const { t } = useTranslation('codeGraph');
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const set = (patch: Partial<DisplaySettings>) => onChange({ ...settings, ...patch });

  const isDefault =
    settings.edgeBrightness === DEFAULT_DISPLAY_SETTINGS.edgeBrightness &&
    settings.nodeGlow === DEFAULT_DISPLAY_SETTINGS.nodeGlow &&
    settings.bloom === DEFAULT_DISPLAY_SETTINGS.bloom;

  return (
    <div ref={rootRef} className="code-graph-display-menu">
      <button
        type="button"
        className="code-graph-display-menu__trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="dialog"
        title={t('codeGraph:display.triggerTitle')}
      >
        {t('codeGraph:display.trigger')}
        {!isDefault && <span className="code-graph-display-menu__dot" aria-hidden />}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('codeGraph:display.dialogAria')}
          className="code-graph-display-menu__panel glass-card glass-card--overview-inner"
        >
          <div className="code-graph-display-menu__header">
            <span className="code-graph-display-menu__title">
              {t('codeGraph:display.contrast')}
            </span>
            <button
              type="button"
              className="code-graph-display-menu__reset"
              onClick={() => onChange({ ...DEFAULT_DISPLAY_SETTINGS })}
              disabled={isDefault}
            >
              {t('codeGraph:display.reset')}
            </button>
          </div>

          <SliderRow
            label={t('codeGraph:display.edgeBrightness')}
            hint={t('codeGraph:display.edgeBrightnessHint')}
            value={settings.edgeBrightness}
            min={DISPLAY_LIMITS.edgeBrightness.min}
            max={DISPLAY_LIMITS.edgeBrightness.max}
            onChange={(edgeBrightness) => set({ edgeBrightness })}
          />
          <SliderRow
            label={t('codeGraph:display.nodeGlow')}
            hint={t('codeGraph:display.nodeGlowHint')}
            value={settings.nodeGlow}
            min={DISPLAY_LIMITS.nodeGlow.min}
            max={DISPLAY_LIMITS.nodeGlow.max}
            onChange={(nodeGlow) => set({ nodeGlow })}
          />
          <SliderRow
            label="Bloom"
            hint={t('codeGraph:display.bloomHint')}
            value={settings.bloom}
            min={DISPLAY_LIMITS.bloom.min}
            max={DISPLAY_LIMITS.bloom.max}
            onChange={(bloom) => set({ bloom })}
          />

          <p className="code-graph-display-menu__footer">{t('codeGraph:display.footer')}</p>
        </div>
      )}
    </div>
  );
}
