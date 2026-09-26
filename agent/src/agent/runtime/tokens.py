"""Per-model context-window resolution: settings-driven window and output
limits as pure arithmetic.

The model is the primary context manager, so the harness owes it accurate
facts about its own window:
- Limits resolve per model first (agent.context.model_profiles), falling back
  to the global defaults (agent.context.window_tokens /
  agent.context.max_output_tokens). Values the user enters must match the
  model's real parameters; malformed entries fall back instead of raising.

Lives in the runtime layer (below context) so both the runtime output cap
and the context layer can depend on it without an upward edge; the settings
keys keep their frozen agent.context.* names. Estimates feed awareness and
auto-compact triggering only; billing relies on provider-reported usage
(Meter / meter_store).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent.contracts import SettingsReader

log = logging.getLogger("agent.runtime.tokens")

#: Defaults when neither the global keys nor a model profile say otherwise
DEFAULT_WINDOW_TOKENS = 200_000
DEFAULT_MAX_OUTPUT_TOKENS = 64_000


@dataclass(frozen=True)
class ContextWindow:
    """Resolved per-model window limits (tokens)."""

    window_tokens: int = DEFAULT_WINDOW_TOKENS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS

    @property
    def usable(self) -> int:
        """Tokens available for the transcript: the window minus the room the
        reply needs. Floor at 1 so percent math never divides by zero."""
        return max(self.window_tokens - self.max_output_tokens, 1)


def _int_or(value: Any, fallback: int) -> int:
    """Non-positive or malformed values count as unset."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


#: Models already warned about (process lifetime, one log line each): an
#: unknown model runs on the conservative global defaults, and the operator
#: should hear about it exactly once instead of every call.
_WARNED_MODELS: set[str] = set()


def resolve_window(settings: SettingsReader, model_name: str = "") -> ContextWindow:
    """Resolve the window limits: global defaults first, then the model's
    profile entry (agent.context.model_profiles) when one matches.

    Malformed shapes (non-dict profiles, non-dict entry, bad numbers) fall
    back to the next source instead of raising - a bad setting must never
    cripple context accounting. A model with no profile entry runs on the
    global defaults and logs one warning (profiles must stay in sync with
    the models the llm domain serves).
    """
    window = _int_or(settings.get("agent.context.window_tokens"), DEFAULT_WINDOW_TOKENS)
    output = _int_or(settings.get("agent.context.max_output_tokens"), DEFAULT_MAX_OUTPUT_TOKENS)
    profiles = settings.get("agent.context.model_profiles")
    if model_name and isinstance(profiles, dict):
        profile = profiles.get(model_name)
        if isinstance(profile, dict):
            window = _int_or(profile.get("window_tokens"), window)
            output = _int_or(profile.get("max_output_tokens"), output)
        elif model_name not in _WARNED_MODELS:
            _WARNED_MODELS.add(model_name)
            log.warning(
                'no context profile for model "%s": using the global defaults; '
                'add agent.context.model_profiles["%s"] with the real window',
                model_name,
                model_name,
            )
    return ContextWindow(window_tokens=window, max_output_tokens=output)


__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_WINDOW_TOKENS",
    "ContextWindow",
    "resolve_window",
]
