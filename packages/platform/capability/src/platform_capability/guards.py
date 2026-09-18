"""Entry-point guards: authentication, rate-limit quota, and audit.

Responsibilities:
- execute(): run the guard chain (auth -> quota -> handler -> audit) for
  every capability invocation
- LocalAuth: reject actors lacking the required scope
- CostQuota: per-actor daily call/cost sliding record (429 on excess)
- AuditSink: persist an AuditEntry per call (InMemory sink included)

Enforced at the framework layer; handlers never implement these themselves.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from platform_actor import ActorContext
from platform_contracts import ActorKind, ErrorSuffix, JobRef, ServiceError

if TYPE_CHECKING:  # avoids a runtime circular import; concrete type only needed for static checks
    from platform_capability.registry import Registry

_DOMAIN = "capability"

#: Input keys that must be redacted in audit summaries (substring match, case-insensitive)
SENSITIVE_KEYS = (
    "api_key",
    "api-key",
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "credential",
)


@dataclass(frozen=True)
class CallRequest:
    capability: Any  # Capability (structural duck typing to avoid a circular import)
    actor: ActorContext | None
    args: dict[str, Any]


@dataclass(frozen=True)
class AuditEntry:
    actor_id: str
    actor_kind: str
    capability: str
    args_summary: str
    ok: bool
    error_code: str
    trace_id: str
    ts: float = field(default_factory=time.time)
    ms: float = 0.0  # execution duration when the caller times it (hooks); informational


class AuditSink(Protocol):
    def record(self, entry: AuditEntry) -> None: ...


def summarize_args(args: dict[str, Any], limit: int = 200) -> str:
    """Input summary for audit records: redacted and truncated."""
    redacted = {
        k: ("***" if any(s in k.lower() for s in SENSITIVE_KEYS) else v) for k, v in args.items()
    }
    text = repr(redacted)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class LocalAuth:
    """Local authentication: user actors are always trusted; agent/external
    actors must hold every scope the capability requires."""

    def __call__(self, req: CallRequest) -> None:
        if req.actor is None:
            raise ServiceError(_DOMAIN, ErrorSuffix.AUTH_REQUIRED, "missing actor credentials")
        if req.actor.actor.kind is ActorKind.USER:
            return
        missing = [s for s in req.capability.scopes if not req.actor.has_scope(s)]
        if missing:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                f"missing scopes: {', '.join(missing)}",
                hint="grant the actor the required capability scopes on the settings page",
            )


class CostQuota:
    """Capability quota: deducts capability.cost against a per-actor daily
    budget; over budget raises RATE_LIMITED.

    Best-effort semantics: usage is an in-process counter, reset on restart,
    tracked independently per runtime instance. Move to shared storage when
    hard enforcement is needed.
    """

    def __init__(
        self, default_daily_budget: int = 1000, budgets: dict[str, int] | None = None
    ) -> None:
        self._default = default_daily_budget
        self._budgets = dict(budgets or {})
        self._usage: dict[tuple[str, str], int] = {}  # (actor_id, day) -> used
        # Read-modify-write must be atomic: handlers run on to_thread workers
        # and bridging threads call concurrently; without the lock they would
        # overwrite each other's counts.
        self._lock = threading.Lock()

    def __call__(self, req: CallRequest) -> None:
        actor_id = req.actor.actor.id if req.actor else "anonymous"
        budget = self._budgets.get(actor_id, self._default)
        day = time.strftime("%Y-%m-%d")
        with self._lock:
            self._prune_other_days(day)
            used = self._usage.get((actor_id, day), 0)
            if used + req.capability.cost > budget:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.RATE_LIMITED,
                    f"daily quota would be exceeded: {used}+{req.capability.cost}/{budget}",
                    hint="resets the next day, or adjust the quota on the settings page",
                )
            self._usage[(actor_id, day)] = used + req.capability.cost

    def _prune_other_days(self, today: str) -> None:
        """Evict stale keys from previous days: usage only matters on its own
        day, and without pruning the dict would grow without bound."""
        for key in [k for k in self._usage if k[1] != today]:
            del self._usage[key]

    def usage(self, actor_id: str) -> tuple[int, int]:
        """Return (used today, budget). Reads take the same lock as __call__'s
        read-modify-write."""
        day = time.strftime("%Y-%m-%d")
        with self._lock:
            return (
                self._usage.get((actor_id, day), 0),
                self._budgets.get(actor_id, self._default),
            )


class InMemoryAuditSink:
    """In-memory audit sink for development/tests; production wires a
    SqliteAuditSink (see audit_db) at the composition root."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


def _record(sinks: list[AuditSink | Callable[[AuditEntry], None]], entry: AuditEntry) -> None:
    for sink in sinks:
        if hasattr(sink, "record"):
            sink.record(entry)  # type: ignore[union-attr]
        else:
            sink(entry)  # type: ignore[operator]


async def execute(
    registry: Registry,
    name: str,
    actor: ActorContext | None,
    args: dict[str, Any] | None = None,
    *,
    auth: list[Callable[[CallRequest], None]] | None = None,
    quota: list[Callable[[CallRequest], None]] | None = None,
    audit: list[AuditSink | Callable[[AuditEntry], None]] | None = None,
) -> Any:
    """Unified execution entry: lookup -> auth -> quota -> validate input ->
    invoke -> audit.

    The order is the semantics: guards run before business logic; an audit
    entry (with trace_id) is recorded regardless of outcome. Internally split
    into _run_guards (pure guards) and _invoke (validation + call) so each
    can be tested independently; this function only orchestrates and
    finalizes auditing.
    """
    args = dict(args or {})
    cap = registry.get(name)
    req = CallRequest(capability=cap, actor=actor, args=args)
    sinks = list(audit or [])

    def entry(ok: bool, error_code: str) -> AuditEntry:
        return AuditEntry(
            actor_id=actor.actor.id if actor else "anonymous",
            actor_kind=actor.actor.kind.value if actor else "none",
            capability=name,
            args_summary=summarize_args(args),
            ok=ok,
            error_code=error_code,
            trace_id=actor.trace_id if actor else "",
        )

    try:
        _run_guards(req, auth=auth, quota=quota)
        result = await _invoke(registry, cap, actor, args, name=name)
    except ServiceError as exc:
        await asyncio.to_thread(_record, sinks, entry(False, exc.body.code))
        raise
    except Exception:  # unexpected failures are also audited (INTERNAL), then re-raised
        await asyncio.to_thread(_record, sinks, entry(False, "CAPABILITY.INTERNAL"))
        raise
    await asyncio.to_thread(_record, sinks, entry(True, ""))
    return result


def _run_guards(
    req: CallRequest,
    *,
    auth: list[Callable[[CallRequest], None]] | None,
    quota: list[Callable[[CallRequest], None]] | None,
) -> None:
    """Guard phase: auth (LocalAuth by default) then quota; failures reject
    with ServiceError."""
    auth_hooks = [LocalAuth()] if auth is None else auth
    for hook in auth_hooks:
        hook(req)
    for hook in quota or ():
        hook(req)


def _check_required_params(
    domain: str,
    params: Mapping[str, inspect.Parameter],
    args: dict[str, Any],
) -> None:
    """Reject a keyword call that would miss required handler parameters with
    INVALID_INPUT: without an input_model there is no coerce step, so a
    missing argument would otherwise surface as a TypeError (500)."""
    missing = [
        p.name
        for p in params.values()
        if p.name != "_actor"
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        and p.default is inspect.Parameter.empty
        and p.name not in args
    ]
    if missing:
        raise ServiceError(
            domain,
            ErrorSuffix.INVALID_INPUT,
            f"missing required inputs: {', '.join(missing)}",
        )


async def _invoke(
    registry: Registry,
    cap,
    actor: ActorContext | None,
    args: dict[str, Any],
    *,
    name: str,
) -> Any:
    """Invoke phase: input validation (coerce) -> _actor injection -> handler
    -> long-running return contract."""
    from platform_capability.define import coerce_input

    input_obj = coerce_input(cap.input_model, args, domain=registry.domain)
    # Convention: when the handler declares an _actor parameter, the caller's
    # ActorRef is injected (operations like writing secrets need to know who
    # is calling); handlers that do not declare it never see it.
    params = inspect.signature(cap.handler).parameters
    if cap.input_model is None:
        _check_required_params(registry.domain, params, args)
    inject = {"_actor": actor.actor} if (actor is not None and "_actor" in params) else {}

    def _call() -> Any:
        if cap.input_model is not None:
            return cap.handler(input_obj, **inject)
        return cap.handler(**args, **inject)

    # Sync handlers (typically short sqlite queries) run off the event loop;
    # async handlers (incl. awaiting the LLM) stay on it.
    if inspect.iscoroutinefunction(cap.handler):
        result = _call()
        if inspect.isawaitable(result):
            result = await result
    else:
        result = await asyncio.to_thread(_call)
    if cap.long_running and not isinstance(result, JobRef):
        raise ServiceError(
            registry.domain,
            ErrorSuffix.INTERNAL,
            f"long-running capability {name} must return JobRef "
            f"(a synchronous long-running result is a defect, §7.3)",
        )
    if cap.streaming and not hasattr(result, "__aiter__"):
        raise ServiceError(
            registry.domain,
            ErrorSuffix.INTERNAL,
            f"streaming capability {name} must return an async iterable (AsyncIterator), got "
            f"{type(result).__name__} (baseline 2026-09 contract)",
        )
    return result
