"""Mode registry: the mode -> runner mapping, filled by each mode module at
its import time, so base.run_mode never imports the mode modules and the
dependency graph stays one-way (package __init__ -> modes -> base -> this
registry).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

_RUNNERS: dict[Any, Callable[..., Awaitable[str]]] = {}


def register_mode(mode: Any, runner: Callable[..., Awaitable[str]]) -> None:
    """Register one mode's runner (called at mode-module import time;
    re-registration overwrites, keeping imports idempotent)."""
    _RUNNERS[mode] = runner


def runner_for(mode: Any) -> Callable[..., Awaitable[str]]:
    """The runner for one mode; an unregistered mode fails with a readable
    error instead of a bare KeyError."""
    try:
        return _RUNNERS[mode]
    except KeyError:
        raise ValueError(f"未知模式: {mode}") from None


__all__ = ["register_mode", "runner_for"]
