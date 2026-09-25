"""Episode recorder: one episodic entry per tool call (trigger / action /
result summary), resolved from the executing instance.

Called by the tool pipeline after post_tool; the pipeline stays a caller —
what to record, how much to keep, and where the run/goal come from live
here. The executing instance arrives as an injected TurnScope provider
(wired by the composition root), so the memory layer never imports the
engine or runtime packages. Truncation caps every stored field so a huge tool result never bloats
episodic.db; retention is enforced by Memory.purge (agent.memory.retention_days).
The organizer reads these rows by `kind="tool"` and groups them per run_id,
so `summary` is exactly the tool name.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from agent.contracts import TurnScope
from agent.memory.episodic import EpisodicMemory

log = logging.getLogger("agent.memory.recorder")

#: Argument keys that name the object a tool acts on, in preference order
_TARGET_KEYS = ("path", "url", "command", "query", "name", "id", "session_id", "title")
_MAX_FIELD = 200


def _target(arguments: dict[str, Any]) -> str:
    for key in _TARGET_KEYS:
        value = arguments.get(key)
        if value not in (None, ""):
            return str(value)[:_MAX_FIELD]
    try:
        blob = json.dumps(arguments, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        blob = str(arguments)
    return blob[:_MAX_FIELD]


class EpisodeRecorder:
    def __init__(self, episodic: EpisodicMemory, current: Callable[[], TurnScope | None]) -> None:
        self._episodic = episodic
        self._current = current

    def record_tool(self, name: str, arguments: dict[str, Any], ok: bool, result: str) -> None:
        """Persist one tool-call episode; never raises into the pipeline (a
        memory write must not fail the tool call — the miss is logged)."""
        inst = self._current()
        run_id = str(getattr(getattr(inst, "state", None), "run_id", "") or "")
        goal = str(getattr(getattr(inst, "task", None), "goal", "") or "")
        detail = {
            "trigger": goal[:_MAX_FIELD],
            "action": {"tool": name, "target": _target(arguments or {})},
            "result": (result or "")[:_MAX_FIELD],
            "ok": bool(ok),
        }
        try:
            self._episodic.log("tool", name, detail, run_id=run_id)
        except Exception:  # degraded memory must not break execution
            log.warning("episodic write failed for tool %s", name, exc_info=True)


__all__ = ["EpisodeRecorder"]
