/**
 * @file Switch
 * @description Shared toggle switch (button role="switch"). Reuses the
 * .llm-switch CSS from the LLM settings tab so every switch in the app shares
 * one visual: same track, knob travel, and press feedback.
 */

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  ariaLabel: string;
  disabled?: boolean;
  /** Small variant for dense list rows. */
  small?: boolean;
}

export function Switch({ checked, onChange, ariaLabel, disabled, small }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      className={`llm-switch${small ? ' llm-switch--sm' : ''}${checked ? ' is-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className="llm-switch__knob" />
    </button>
  );
}
