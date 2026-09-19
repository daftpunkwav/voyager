"""ContextVar carrying the instance whose turn is executing, so
meta tools (context_status / compact_context) can reach the live transcript
without threading instance references through the toolbelt.

The variable is set at run_turn entry and reset in its finally; it is None
outside a turn (tool handlers only ever run inside one, so the None branch
is a defensive fallback, not a reachable steady state).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

current_instance: ContextVar[Any] = ContextVar("agent.current_instance", default=None)


def current_session() -> str:
    """Chat session id of the executing instance ('' outside a turn or for
    session-less work). The routing key UI-facing projections (ask dialogs,
    per-session plans) stamp on their events so multi-session frontends can
    route them to the right lane."""
    inst = current_instance.get()
    if inst is None:
        return ""
    return str(getattr(getattr(inst, "task", None), "session", "") or "")


__all__ = ["current_instance", "current_session"]
