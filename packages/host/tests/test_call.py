"""Late-bound call / call_sync: missing domain, arg validation,
and the running-loop guard on call_sync.
"""

from __future__ import annotations

import pytest
from host.call import bind_calls
from platform_capability import Registry, Wiring, capability
from platform_contracts import ActorKind, ActorRef


def _echo_wiring() -> dict[str, Wiring]:
    reg = Registry("alpha")

    @capability(reg, name="echo", description="echo")
    def echo(text: str = "") -> dict:
        return {"echo": text}

    return {"alpha": Wiring(registry=reg, probe=lambda: {"status": "up"})}


def test_call_sync_roundtrip_and_missing_domain() -> None:
    _, call_sync = bind_calls(_echo_wiring(), audit=[], quota=[])
    assert call_sync("alpha", "echo", {"text": "hi"}) == {"echo": "hi"}
    with pytest.raises(RuntimeError, match="not wired"):
        call_sync("ghost", "echo", {})


def test_call_rejects_bad_args() -> None:
    _, call_sync = bind_calls(_echo_wiring(), audit=[], quota=[])
    with pytest.raises(RuntimeError, match="domain"):
        call_sync("", "echo", {})
    with pytest.raises(RuntimeError, match="name"):
        call_sync("alpha", "", {})
    with pytest.raises(TypeError, match="dict"):
        call_sync("alpha", "echo", ["not", "a", "dict"])  # type: ignore[arg-type]


async def test_call_async_and_call_sync_rejects_running_loop() -> None:
    call, call_sync = bind_calls(_echo_wiring(), audit=[], quota=[])
    assert await call("alpha", "echo", {"text": "x"}) == {"echo": "x"}
    with pytest.raises(RuntimeError, match="event-loop"):
        call_sync("alpha", "echo", {"text": "x"})


def test_host_actor_wildcard_passes_scoped_capability() -> None:
    """SYSTEM host.call holds '*', so a capability that declares scopes still
    runs through the same execute() guard chain."""
    reg = Registry("alpha")

    @capability(reg, name="guarded", description="needs a scope", scopes=("alpha.admin",))
    def guarded() -> dict:
        return {"ok": True}

    wirings = {"alpha": Wiring(registry=reg, probe=lambda: {"status": "up"})}
    _, call_sync = bind_calls(wirings, audit=[], quota=[])
    assert call_sync("alpha", "guarded", {}) == {"ok": True}


def test_empty_scope_actor_would_fail_without_wildcard() -> None:
    from platform_contracts import ServiceError

    reg = Registry("alpha")

    @capability(reg, name="guarded", description="needs a scope", scopes=("alpha.admin",))
    def guarded() -> dict:
        return {"ok": True}

    wirings = {"alpha": Wiring(registry=reg, probe=lambda: {"status": "up"})}
    bare = ActorRef(kind=ActorKind.SYSTEM, id="bare")
    _, call_sync = bind_calls(wirings, actor=bare, audit=[], quota=[])
    with pytest.raises(ServiceError) as exc:
        call_sync("alpha", "guarded", {})
    assert exc.value.body.code == "CAPABILITY.FORBIDDEN"
