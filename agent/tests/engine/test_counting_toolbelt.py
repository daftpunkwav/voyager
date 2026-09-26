"""Tests for the composite modes' CountingToolbelt: invocation-level call
accounting and the on_progress compatibility fallback's re-execution gate.

The fallback must only fire for a signature-level TypeError (an inner surface
without the on_progress kwarg, raised before the handler runs) — a TypeError
raised AFTER the handler executed must propagate unchanged, or the tool's side
effects would run twice.
"""

from __future__ import annotations

from typing import Any

import pytest
from agent.engine.modes.base import CountingToolbelt
from agent.llm import ToolCall

_CALL = ToolCall("c1", "t", {})


class _ModernInner:
    """Full surface: accepts on_progress, records every execution."""

    def __init__(self) -> None:
        self.executions = 0

    async def call_detailed(self, call: ToolCall, *args: Any, on_progress: Any = None) -> Any:
        self.executions += 1
        return "ok"


class _LegacyInner:
    """Signature-level incompatibility: the kwarg is rejected before running."""

    def __init__(self) -> None:
        self.executions = 0

    async def call_detailed(self, call: ToolCall) -> Any:
        self.executions += 1
        return "ok"


class _BrokenInner:
    """The handler ran (side effect done), then metering blew up with an
    unrelated TypeError — the fallback must NOT re-execute it."""

    def __init__(self) -> None:
        self.executions = 0

    async def call_detailed(self, call: ToolCall, *args: Any, on_progress: Any = None) -> Any:
        self.executions += 1
        raise TypeError("unsupported operand type(s) for -: 'int' and 'str'")


async def test_counts_one_call_per_invocation() -> None:
    inner = _ModernInner()
    belt = CountingToolbelt(inner)
    result = await belt.call_detailed(_CALL, on_progress=None)
    assert result == "ok"
    assert belt.calls == 1
    assert inner.executions == 1


async def test_legacy_inner_falls_back_without_on_progress() -> None:
    inner = _LegacyInner()
    belt = CountingToolbelt(inner)
    result = await belt.call_detailed(_CALL, on_progress=None)
    assert result == "ok"
    assert belt.calls == 1
    assert inner.executions == 1


async def test_post_handler_typeerror_never_reexecutes() -> None:
    inner = _BrokenInner()
    belt = CountingToolbelt(inner)
    with pytest.raises(TypeError, match="operand"):
        await belt.call_detailed(_CALL, on_progress=None)
    assert inner.executions == 1  # the fallback did not run the handler again
    assert belt.calls == 1
