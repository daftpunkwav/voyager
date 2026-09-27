"""Tests for guards: auth, quota, audit, and the long-running contract."""

from dataclasses import dataclass
from typing import Any

import pytest
from platform_actor import ActorContext
from platform_capability import (
    CostQuota,
    InMemoryAuditSink,
    Registry,
    capability,
    execute,
    summarize_args,
)
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, JobRef, ServiceError


@dataclass
class _In:
    text: str
    api_key: str = ""


def _registry(long_running: bool = False) -> Registry:
    reg = Registry("notes")

    @capability(
        reg,
        name="do_thing",
        description="test capability",
        input_model=_In,
        cost=5,
        scopes=("notes.write",),
        long_running=long_running,
    )
    async def do_thing(data: _In):
        if long_running:
            return JobRef(job_id="j-1")
        return {"ok": data.text}

    return reg


USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(
    actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=("notes.write",))
)
STRANGER_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.other", scopes=()))


class TestAuth:
    async def test_user_always_allowed(self) -> None:
        assert await execute(_registry(), "do_thing", USER_CTX, {"text": "x"}) == {"ok": "x"}

    async def test_agent_with_scope_allowed(self) -> None:
        assert await execute(_registry(), "do_thing", AGENT_CTX, {"text": "x"}) == {"ok": "x"}

    async def test_agent_without_scope_forbidden(self) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(_registry(), "do_thing", STRANGER_CTX, {"text": "x"})
        assert exc.value.body.code == "CAPABILITY.FORBIDDEN"
        assert exc.value.http_status == 403

    async def test_no_actor_auth_required(self) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(_registry(), "do_thing", None, {"text": "x"})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"
        assert exc.value.http_status == 401


class TestQuota:
    async def test_quota_exceeded(self) -> None:
        quota = CostQuota(default_daily_budget=9)  # cost=5: second call 5+5>9
        reg = _registry()
        await execute(reg, "do_thing", USER_CTX, {"text": "a"}, quota=[quota])
        with pytest.raises(ServiceError) as exc:
            await execute(reg, "do_thing", USER_CTX, {"text": "b"}, quota=[quota])
        assert exc.value.body.code == "CAPABILITY.RATE_LIMITED"
        assert exc.value.http_status == 429
        assert quota.usage("local") == (5, 9)


class TestAudit:
    async def test_success_and_failure_recorded(self) -> None:
        sink = InMemoryAuditSink()
        reg = _registry()
        await execute(reg, "do_thing", USER_CTX, {"text": "a"}, audit=[sink])
        with pytest.raises(ServiceError):
            await execute(reg, "do_thing", STRANGER_CTX, {"text": "b"}, audit=[sink])
        assert [e.ok for e in sink.entries] == [True, False]
        assert sink.entries[1].error_code == "CAPABILITY.FORBIDDEN"
        assert sink.entries[0].trace_id  # trace_id propagated end to end

    def test_args_summary_redacts_secrets(self) -> None:
        summary = summarize_args({"text": "hello", "api_key": "sk-xxx"})
        assert "sk-xxx" not in summary
        assert "***" in summary
        assert "hello" in summary

    def test_args_summary_redacts_credential_variants(self) -> None:
        """credential / api-key variants are redacted too (substring match)."""
        summary = summarize_args({"user_credential": "c1", "api-key": "k2"})
        assert "c1" not in summary and "k2" not in summary


class TestLongRunning:
    async def test_job_ref_passes(self) -> None:
        ref = await execute(_registry(long_running=True), "do_thing", USER_CTX, {"text": "x"})
        assert isinstance(ref, JobRef)

    async def test_sync_result_rejected_for_long_running(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="bad", description="broken long-running", long_running=True)
        def bad() -> dict:
            return {"sync": True}  # sync long-running results are treated as a defect

        with pytest.raises(ServiceError, match="JobRef"):
            await execute(reg, "bad", USER_CTX, {})

    async def test_sync_handler_supported(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="ping", description="ping")
        def ping() -> dict:
            return {"pong": True}

        assert await execute(reg, "ping", USER_CTX, {}) == {"pong": True}


class TestActorInjection:
    """When the handler declares _actor, the caller's ActorRef is injected;
    without the declaration it is invisible."""

    async def test_actor_injected_when_declared(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="whoami", description="echo caller")
        def whoami(_actor: ActorRef | None = None) -> dict:
            return {"id": _actor.id if _actor else None}

        out = await execute(reg, "whoami", AGENT_CTX, {})
        assert out == {"id": "agent.main"}

    async def test_actor_not_injected_when_not_declared(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="ping2", description="no _actor parameter")
        def ping2() -> dict:
            return {"pong": True}

        assert await execute(reg, "ping2", AGENT_CTX, {}) == {"pong": True}


class TestRequiredParamsWithoutModel:
    """Without an input_model there is no coerce step: a keyword call missing
    a required handler parameter must be rejected as INVALID_INPUT, not die
    as a TypeError (500) inside the invocation."""

    async def test_missing_required_param_400(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="greet", description="needs a name")
        async def greet(name: str, greeting: str = "hi") -> dict:
            return {"text": f"{greeting} {name}"}

        with pytest.raises(ServiceError) as exc:
            await execute(reg, "greet", USER_CTX, {})
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert "name" in exc.value.body.message

    async def test_satisfied_call_still_passes(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="greet2", description="needs a name")
        async def greet(name: str) -> dict:
            return {"text": f"hi {name}"}

        assert await execute(reg, "greet2", USER_CTX, {"name": "x"}) == {"text": "hi x"}


class TestSignatureBinding:
    """Signature.bind is the contract enforcement for un-modelled handlers:
    unknown keys and missing arguments become INVALID_INPUT (the broadcast
    schema is true at runtime), while a TypeError raised *inside* the handler
    body still propagates untouched."""

    async def test_unknown_key_is_invalid_input_not_typeerror(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="greet3", description="needs a name")
        async def greet(name: str) -> dict:
            return {"text": f"hi {name}"}

        with pytest.raises(ServiceError) as exc:
            await execute(reg, "greet3", USER_CTX, {"name": "x", "bogus": 1})
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert "bogus" in exc.value.body.message

    async def test_shallow_type_mismatch_is_invalid_input(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="page", description="list with a limit")
        async def page(limit: int = 10) -> dict:
            return {"limit": limit}

        with pytest.raises(ServiceError) as exc:
            await execute(reg, "page", USER_CTX, {"limit": "abc"})
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_shallow_check_skips_unannotated_and_injected(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="flex", description="untyped params pass through")
        async def flex(value) -> dict:  # no annotation: left to the handler
            return {"value": value}

        assert await execute(reg, "flex", USER_CTX, {"value": "abc"}) == {"value": "abc"}

    async def test_typeerror_inside_handler_propagates(self) -> None:
        """A genuine bug inside the handler must NOT be masked as a client
        error: the bind check never enters the handler body."""
        reg = Registry("agent")

        @capability(reg, name="buggy", description="raises TypeError inside")
        async def buggy(name: str) -> dict:
            sneak: Any = name  # hides the operand from mypy; runtime still str + int
            return {"text": sneak + 1}

        with pytest.raises(TypeError):
            await execute(reg, "buggy", USER_CTX, {"name": "x"})

    async def test_missing_param_error_carries_signature_hint(self) -> None:
        reg = Registry("agent")

        @capability(reg, name="greet4", description="needs a name")
        async def greet(name: str, greeting: str = "hi") -> dict:
            return {"text": f"{greeting} {name}"}

        with pytest.raises(ServiceError) as exc:
            await execute(reg, "greet4", USER_CTX, {})
        assert "missing a required argument" in exc.value.body.message
        # The hint names the full handler signature so the caller can fix
        # the input in one round trip
        assert "greeting" in (exc.value.body.hint or "")
        assert "name" in (exc.value.body.hint or "")

    async def test_modelled_capability_unchanged(self) -> None:
        reg = _registry()
        out = await execute(reg, "do_thing", AGENT_CTX, {"text": "hello"})
        assert out == {"ok": "hello"}


class TestAuthAlwaysOn:
    """There is no caller-supplied way to switch authentication off: the
    auth parameter is gone and LocalAuth always runs (a nominally-empty hook
    list used to be a fail-open trap)."""

    async def test_agent_without_scope_still_rejected(self) -> None:
        reg = Registry("notes")

        @capability(reg, name="w", description="scoped write", scopes=("notes.write",))
        async def w() -> dict:
            return {"ok": True}

        outsider = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="a.x", scopes=()))
        with pytest.raises(ServiceError) as exc:
            await execute(reg, "w", outsider, {})
        assert "AUTH" in exc.value.body.code or exc.value.body.code.endswith("FORBIDDEN")

    async def test_execute_rejects_auth_kwarg(self) -> None:
        """Passing the retired auth kwarg is a TypeError at the call site, not
        a silently honoured hook list."""
        reg = Registry("notes")

        @capability(reg, name="r", description="read")
        async def r() -> dict:
            return {"ok": True}

        # **-expansion keeps the retired kwarg out of mypy's view of this
        # call site while the runtime still rejects it
        legacy: dict[str, Any] = {"auth": []}
        with pytest.raises(TypeError):
            await execute(reg, "r", USER_CTX, {}, **legacy)
