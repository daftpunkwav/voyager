"""Round-limit assembly: settings -> ModeLimits.

Same domain as ModeLimits; overrides can only be stricter than the global
default, and 0 / unset means unlimited (same sentinel as
agent.rounds.max_tokens) — a long task may run as long as its rounds do.
"""

from __future__ import annotations

from agent.contracts import SettingsReader
from agent.engine.modes import ModeLimits

#: Built-in defaults (the floor when settings are unconfigured): no cap.
DEFAULT_LIMITS = ModeLimits()


def limits_from_settings(
    settings: SettingsReader,
    *,
    max_rounds: int | None = None,
    max_tool_calls: int | None = None,
    max_tokens: int | None = None,
) -> ModeLimits:
    """Assemble round limits: globals read fresh from settings each call;
    0 / negative / unset means unlimited (never falls back to a built-in cap);
    a positive dispatch override tightens (min) but never introduces a cap
    when the global is unlimited."""

    def _cap(override: int | None, key: str) -> int:
        try:
            global_v = int(settings.get(key))
        except (TypeError, ValueError):
            global_v = 0
        global_v = max(0, global_v)
        if override is None or override <= 0:
            return global_v
        return min(override, global_v) if global_v > 0 else override

    def _tokens() -> int:
        """Token budget: only a positive global counts; 0 = unlimited."""
        try:
            global_v = int(settings.get("agent.rounds.max_tokens"))
        except (TypeError, ValueError):
            global_v = 0
        if max_tokens is not None and max_tokens > 0:
            return min(max_tokens, global_v) if global_v > 0 else max_tokens
        return max(0, global_v)

    return ModeLimits(
        max_rounds=_cap(max_rounds, "agent.rounds.max"),
        max_tool_calls=_cap(max_tool_calls, "agent.rounds.tool_max"),
        max_tokens=_tokens(),
    )


__all__ = ["DEFAULT_LIMITS", "limits_from_settings"]
