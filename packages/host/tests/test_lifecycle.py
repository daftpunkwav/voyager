"""Start-order rollback: a later domain's start failure stops
already-started domains; stop/close failures do not abort the rest.
"""

from __future__ import annotations

import pytest
from host.lifecycle import close_wirings, start_wirings, stop_wirings
from platform_capability import Registry, Wiring


def _reg(name: str) -> Registry:
    return Registry(name)


async def test_start_failure_stops_already_started() -> None:
    started: list[str] = []
    stopped: list[str] = []

    async def start_a() -> None:
        started.append("a")

    async def start_b() -> None:
        started.append("b")
        raise RuntimeError("b-start-failed")

    async def stop_a() -> None:
        stopped.append("a")

    async def stop_b() -> None:
        stopped.append("b")

    wirings = {
        "a": Wiring(registry=_reg("a"), start=start_a, stop=stop_a),
        "b": Wiring(registry=_reg("b"), start=start_b, stop=stop_b),
    }
    with pytest.raises(RuntimeError, match="b-start-failed"):
        await start_wirings(wirings)
    assert started == ["a", "b"]
    assert stopped == ["a"]  # b never finished start, so it is not rolled back


async def test_stop_continues_after_one_failure() -> None:
    stopped: list[str] = []

    async def stop_a() -> None:
        stopped.append("a")

    async def stop_b() -> None:
        stopped.append("b")
        raise RuntimeError("b-stop-failed")

    wirings = [
        Wiring(registry=_reg("a"), stop=stop_a),
        Wiring(registry=_reg("b"), stop=stop_b),
    ]
    await stop_wirings(wirings)
    # reverse order: b then a; b's failure must not skip a
    assert stopped == ["b", "a"]


def test_close_continues_after_one_failure() -> None:
    closed: list[str] = []

    def close_a() -> None:
        closed.append("a")

    def close_b() -> None:
        closed.append("b")
        raise RuntimeError("b-close-failed")

    close_wirings(
        [
            Wiring(registry=_reg("a"), close=close_a),
            Wiring(registry=_reg("b"), close=close_b),
        ]
    )
    assert closed == ["b", "a"]
