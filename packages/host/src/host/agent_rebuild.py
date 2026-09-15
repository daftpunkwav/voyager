"""Restartless agent workspace rebuild: switch the agent's working directory
without restarting the service process.

Switching means rebuilding the agent app (jail roots, shell cwd, skills,
hooks, spill/scratchpad/todo paths, MCP cwd, scoped rules) around the new
workspace while everything else stays up: the event bus/log, settings,
secrets, audit, quota and all domain wirings are shared and untouched, so
chat history, sessions and domain data survive. In-flight turns are drained
(first) or cancelled (on timeout) before the old app closes; messages sent
during the swap wait in the event log and are picked up by the new loop.

Explicitly out of scope: domain storage roots (notes / sources / graph /
code-exec snapshot the workspace at wire time) do NOT move — only the
agent's working directory and the workspace-bound gateway routers
(uploads, workspace browser, agent REST mount) are rebound. The endpoint
response and the UI copy state this boundary.

Teardown/startup mirror the agent half of the host lifespan in assemble.py;
any drift between the two must be reconciled deliberately.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.app import AgentApp
from agent.build import build_agent
from agent.contracts import Purpose
from agent.llm import LLMClient
from agent.runtime.jobs_view import JobsView

# Canonical settings-key constant (registry lives in agent.settings); aliased
# to keep this module's public name stable.
from agent.settings import WORKSPACE_DIR_KEY as WORKSPACE_KEY
from agent.tools import ensure_workdir
from fastapi import APIRouter, Request
from platform_capability import build_router
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError

from .bridge import make_domain_tools
from .embedder_adapter import ServiceEmbedder
from .jobs_router import make_job_cancel_router
from .lifecycle import close_quietly
from .llm_adapter import ServiceLLM
from .llm_routing import RoutingServiceLLM

log = logging.getLogger("host.agent_rebuild")

#: Route prefixes rebound to the new workspace/agent on switch.
_SWITCH_PREFIXES = ("/api/agent", "/api/workspace", "/api/uploads")


def resolve_candidate_dir(raw: str, root: Path) -> Path:
    """Validate a user-supplied workspace directory with the same rules as
    assembly-time resolution: non-empty, no ``..`` segments, and staying
    inside the repo root. Returns the joined path (absolute input passes
    through, relative input joins onto the root)."""
    text = (raw or "").strip()
    if not text:
        raise ServiceError("host", ErrorSuffix.INVALID_INPUT, "workspace dir must not be empty")
    if ".." in Path(text).parts:
        raise ServiceError(
            "host",
            ErrorSuffix.INVALID_INPUT,
            f"agent.workspace.dir must not contain '..' segments: {text}",
        )
    path = Path(text)
    joined = path if path.is_absolute() else root / path
    if not joined.resolve().is_relative_to(root.resolve()):
        raise ServiceError(
            "host",
            ErrorSuffix.INVALID_INPUT,
            f"agent.workspace.dir must stay inside the repo root: {text}",
        )
    return joined


@dataclass
class AgentRebuilder:
    """Everything switch_workspace needs that outlives one build_agent call.

    mounts is the domain-only mount list (before the agent mount is
    appended); llm is the build() injection or None for ServiceLLM.
    agent/agent_task/mcp_task track the live generation; lifespan assigns
    them at startup, switch_workspace rotates them under lock.
    """

    root: Path
    data_agent_dir: Path
    bus: Any
    event_log: Any
    settings_store: Any
    domain_mounts: list
    call: Any
    call_sync: Any
    audit: list
    quota: list
    issuer: Any
    injected_llm: LLMClient | None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    agent: AgentApp | None = None
    agent_task: asyncio.Task | None = None
    mcp_task: asyncio.Task | None = None
    #: Resolved workspace of the live generation (source of truth for
    #: rollback and the previous field — the settings value may predate an
    #: explicit workspace_dir injection or a direct capability write).
    current_workspace: Path | None = None

    def build_fn(self, workspace: Path) -> AgentApp:
        """Assemble one agent generation around workspace (mirrors the
        build_agent call in assemble.build)."""
        return build_agent(
            data_dir=self.data_agent_dir,
            workspace_dir=workspace,
            llm=self.injected_llm if self.injected_llm is not None else ServiceLLM(self.call),
            bus=self.bus,
            settings_store=self.settings_store,
            extra_tools=make_domain_tools(self.domain_mounts, audit=self.audit, quota=self.quota),
            job_cancel=make_job_cancel_router(self.call, JobsView(self.event_log)),
            audit=self.audit,
            embedder=ServiceEmbedder(self.call_sync, self.settings_store),
            purpose_llms={
                purpose.value: RoutingServiceLLM(
                    self.call, purpose=purpose, settings=self.settings_store, bus=self.bus
                )
                for purpose in (Purpose.ARBITER, Purpose.DISTILL, Purpose.CONTEXT_PLANNER)
            },
        )


async def _teardown_agent(
    old: AgentApp,
    agent_task: asyncio.Task | None,
    mcp_task: asyncio.Task | None,
) -> None:
    """Stop one agent generation: no new turns, drain in-flight work, then
    close its stores (shared bus/log/settings stay open — see owns_*)."""
    old.loop.stop()
    for task in (agent_task, mcp_task):
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
    with suppress(Exception):
        await old.scheduler.stop_queue()
    with suppress(Exception):
        await old.drain()
    with suppress(Exception):
        await old.scheduler.shutdown()
    close_quietly(old, what="agent")


async def _start_agent_tasks(rebuilder: AgentRebuilder, app: AgentApp) -> None:
    """Launch the loop/MCP/queue tasks for a fresh generation (mirrors the
    host lifespan startup)."""
    rebuilder.mcp_task = asyncio.create_task(app.mcp.start())
    rebuilder.agent_task = asyncio.create_task(app.loop.run())
    with suppress(Exception):
        await app.start_queue_loop()


def _route_paths(entry: Any) -> list[str]:
    """Effective paths of one top-level app route entry.

    Recent FastAPI keeps included routers deferred (_IncludedRouter) until
    first use: their paths live on the inner router, prefixed by the include
    context. Plain routes carry the full path directly.
    """
    prefix = ""
    inner = entry
    context = getattr(entry, "include_context", None)
    if context is not None:
        prefix = str(getattr(context, "prefix", "") or "")
        inner = getattr(entry, "original_router", entry)
    routes = getattr(inner, "routes", None)
    if routes is None:
        path = str(getattr(entry, "path", "") or "")
        return [prefix + path] if path else []
    paths = []
    for route in routes:
        path = str(getattr(route, "path", "") or "")
        if path:
            paths.append(prefix + path)
    return paths


def _in_switch_scope(path: str) -> bool:
    return path == "/api/uploads" or any(
        path == prefix or path.startswith(prefix + "/") for prefix in _SWITCH_PREFIXES
    )


def _swap_workspace_routes(
    app: Any, new_agent: AgentApp, workspace: Path, rebuilder: AgentRebuilder
) -> None:
    """Rebind the workspace-dependent routes to the new generation: the agent
    REST mount (fresh capability registry) plus the uploads and workspace
    routers (fresh directory closures). Chat/SSE/session routes read the
    shared log and are untouched."""
    from gateway.uploads import build_upload_router
    from gateway.workspace import build_workspace_router

    app.router.routes[:] = [
        entry
        for entry in app.router.routes
        if not any(_in_switch_scope(p) for p in _route_paths(entry))
    ]
    app.include_router(
        build_router(
            new_agent.registry,
            issuer=rebuilder.issuer,
            auth=None,
            quota=rebuilder.quota,
            audit=rebuilder.audit,
        ),
        prefix="/api/agent",
    )
    app.include_router(build_upload_router(workspace))
    app.include_router(build_workspace_router(workspace))
    # The switch endpoint itself lives under /api/workspace/*, so it was
    # just removed with the old generation: re-mount it (stateless, reads
    # the rebuilder off app.state per request).
    app.include_router(build_switch_router())
    app.openapi_schema = None  # force OpenAPI regen (FastAPI caches on first use)


async def switch_workspace(rebuilder: AgentRebuilder, app: Any, raw_dir: str) -> dict[str, Any]:
    """Validate, rebuild the agent around the new workspace, persist the
    setting, and rebind routes — all under one lock so concurrent switches
    and lifespan shutdown serialize.

    The old generation is torn down before the new one builds (shared sqlite
    files must not be held twice); if the new build fails, the old workspace
    is rebuilt as a rollback and the error still surfaces.
    """
    async with rebuilder.lock:
        target = resolve_candidate_dir(raw_dir, rebuilder.root)
        ensure_workdir(target)
        old = rebuilder.agent
        if old is None:
            raise ServiceError("host", ErrorSuffix.UNAVAILABLE, "agent is not running")
        previous = rebuilder.current_workspace
        if previous is None:
            raw_previous = str(rebuilder.settings_store.get(WORKSPACE_KEY) or "")
            previous = (
                resolve_candidate_dir(raw_previous, rebuilder.root)
                if raw_previous.strip()
                else rebuilder.data_agent_dir.parent / "workspace"
            )
        if previous.resolve() == target.resolve():
            return {
                "workspace": str(target),
                "previous": str(previous),
                "note": "already on this workspace; nothing was rebuilt.",
            }
        await _teardown_agent(old, rebuilder.agent_task, rebuilder.mcp_task)
        rebuilder.agent_task = None
        rebuilder.mcp_task = None
        try:
            new_agent = rebuilder.build_fn(target)
        except Exception as exc:
            log.exception("workspace switch build failed for %s; rolling back", target)
            try:
                ensure_workdir(previous)
                rolled = rebuilder.build_fn(previous)
            except Exception:
                log.exception("workspace rollback failed")
                # Leave no half-torn-down generation behind: the next switch
                # (or lifespan shutdown) sees a clean "not running" state.
                rebuilder.agent = None
                rebuilder.current_workspace = None
                raise ServiceError(
                    "host",
                    ErrorSuffix.UNAVAILABLE,
                    f"workspace switch failed ({exc}); rollback failed too — restart the service",
                ) from exc
            rebuilder.agent = rolled
            rebuilder.current_workspace = previous
            _swap_workspace_routes(app, rolled, previous, rebuilder)
            await _start_agent_tasks(rebuilder, rolled)
            if hasattr(app.state, "backend") and app.state.backend is not None:
                app.state.backend.agent = rolled
            raise ServiceError(
                "host", ErrorSuffix.UNAVAILABLE, f"workspace switch failed ({exc}); rolled back"
            ) from exc
        rebuilder.agent = new_agent
        rebuilder.current_workspace = target
        _swap_workspace_routes(app, new_agent, target, rebuilder)
        await rebuilder.settings_store.set(WORKSPACE_KEY, str(target), LOCAL_USER)
        await _start_agent_tasks(rebuilder, new_agent)
        if hasattr(app.state, "backend") and app.state.backend is not None:
            app.state.backend.agent = new_agent
        return {
            "workspace": str(target),
            "previous": str(previous),
            "note": (
                "agent workspace switched without a service restart; sessions and "
                "history are preserved, in-flight turns were drained. Domain data "
                "(notes, sources, graph) stays where it was."
            ),
        }


def build_switch_router() -> APIRouter:
    """POST /api/workspace/switch {dir}: hot-switch the agent workspace.
    Reads the rebuilder off app.state (set by the host composition root);
    standalone gateway deployments without one get a 503."""
    router = APIRouter()

    @router.post("/api/workspace/switch")
    async def switch(request: Request) -> dict[str, Any]:
        rebuilder = getattr(request.app.state, "agent_rebuilder", None)
        if rebuilder is None:
            raise ServiceError(
                "host",
                ErrorSuffix.UNAVAILABLE,
                "workspace hot-switch unavailable in this deployment",
            )
        try:
            body = await request.json()
        except ValueError:
            raise ServiceError(
                "host", ErrorSuffix.INVALID_INPUT, "request body must be JSON"
            ) from None
        raw = str((body or {}).get("dir") or "")
        return await switch_workspace(rebuilder, request.app, raw)

    return router


__all__ = [
    "WORKSPACE_KEY",
    "AgentRebuilder",
    "build_switch_router",
    "resolve_candidate_dir",
    "switch_workspace",
]
