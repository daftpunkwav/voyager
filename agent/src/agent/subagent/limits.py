"""Round-limit assembly: settings -> ModeLimits.

Same domain as ModeLimits; overrides can only be stricter than the global
default (min wins), and a dirty/unset global value falls back to the
built-in defaults.
"""

from __future__ import annotations

from agent.contracts import SettingsReader
from agent.subagent.modes import ModeLimits

#: Built-in defaults (the floor when settings are unconfigured)
DEFAULT_LIMITS = ModeLimits()


def limits_from_settings(
    settings: SettingsReader,
    *,
    max_rounds: int | None = None,
    max_tool_calls: int | None = None,
    max_tokens: int | None = None,
) -> ModeLimits:
    """Assemble round limits: global defaults are read fresh from settings each
    call; invalid/non-positive overrides count as unset; the effective value is
    min(override, global) - a dispatch tier can only be stricter than global."""
    defaults = (DEFAULT_LIMITS.max_rounds, DEFAULT_LIMITS.max_tool_calls)

    def _cap(override: int | None, key: str, fallback: int) -> int:
        try:
            global_v = int(settings.get(key))
        except (TypeError, ValueError):
            global_v = 0
        if global_v <= 0:
            global_v = fallback
        if override is None or override <= 0:
            return global_v
        return min(override, global_v)

    def _tokens() -> int:
        """Token budget: only a positive global counts; a dispatch override
        can only tighten it. 0 = unlimited."""
        try:
            global_v = int(settings.get("agent.rounds.max_tokens"))
        except (TypeError, ValueError):
            global_v = 0
        if max_tokens is not None and max_tokens > 0:
            return min(max_tokens, global_v) if global_v > 0 else max_tokens
        return max(0, global_v)

    return ModeLimits(
        max_rounds=_cap(max_rounds, "agent.rounds.max", defaults[0]),
        max_tool_calls=_cap(max_tool_calls, "agent.rounds.tool_max", defaults[1]),
        max_tokens=_tokens(),
    )


__all__ = ["DEFAULT_LIMITS", "limits_from_settings"]
