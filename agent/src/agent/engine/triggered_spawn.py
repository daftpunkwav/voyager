"""Event-triggered subagents: a definition with trigger="event:<pattern>"
spawns one task instance per matching event, subject to a per-pattern
cooldown (frequency guard).

Pure consumption: the handler matches current definitions against the event
type and dispatches through master.dispatch_task (same path as chat-driven
spawns, so limits / readonly / network tiers all apply). Patterns registered
at assembly time; definitions added later take effect after a hook reload
(syncs the same subscription channel).
"""

from __future__ import annotations

import fnmatch
import logging
import time
from typing import Any

from platform_contracts import ServiceError

from agent.settings import TRIGGERS_COOLDOWN_KEY

log = logging.getLogger("agent.triggered_spawn")

_DEFAULT_COOLDOWN_S = 300.0


def trigger_patterns(registry: Any) -> tuple[str, ...]:
    """Subscription patterns of all definitions with an event trigger."""
    patterns: list[str] = []
    for d in registry.list():
        if isinstance(d.trigger, str) and d.trigger.startswith("event:"):
            patterns.append(d.trigger[len("event:") :])
    return tuple(dict.fromkeys(patterns))


def make_handler(
    master: Any,
    registry: Any,
    *,
    settings: Any | None = None,
    cooldown_s: float = _DEFAULT_COOLDOWN_S,
) -> Any:
    """EventLoop handler: dispatch every definition whose trigger pattern
    matches the event type, one instance per def, cooldown-guarded."""

    def _cooldown_ok(key: str, now: float) -> bool:
        # cooldown map lives on the handler closure; settings may override the
        # window globally (agent.triggers.cooldown_s via settings, 0 = no guard)
        window = cooldown_s
        if settings is not None:
            try:
                window = float(settings.get(TRIGGERS_COOLDOWN_KEY))
            except (TypeError, ValueError, ServiceError):
                window = cooldown_s
            if window <= 0:
                return True
        last = _last_seen.get(key)
        return last is None or now - last >= window

    _last_seen: dict[str, float] = {}

    async def handler(event) -> None:
        now = time.monotonic()
        for d in registry.list():
            if not isinstance(d.trigger, str) or not d.trigger.startswith("event:"):
                continue
            pattern = d.trigger[len("event:") :]
            if not fnmatch.fnmatchcase(event.type, pattern):
                continue
            key = f"{d.name}:{pattern}"
            if not _cooldown_ok(key, now):
                log.debug("trigger %s suppressed by cooldown", key)
                continue
            _last_seen[key] = now
            goal = f"[trigger {event.type}] {d.description}"
            try:
                await master.dispatch_task(goal, persona=d.name or d.persona)
            except Exception:  # a failed trigger never breaks the loop
                log.exception("triggered spawn failed for %s", d.name)

    return handler


__all__ = ["make_handler", "trigger_patterns"]
