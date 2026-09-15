"""Monolithic composition root: discovers domains by scanning their
module cards, wires shared facilities into each, and mounts domains plus the
agent runtime behind the gateway in a single process on a single port.

Responsibilities:
- Own shared facilities (EventLog/EventBus/SecretStore/SettingsStore/audit/
  issuer/quota) and resolve the workspace directory
- Seed os.environ from the repo-root .env at import time (existing env wins)
- Plan the assembly from scanned cards (host.plan) and wire each
  domain via its wiring.wire() — never a hardcoded domain import list
- Provide late-bound cross-domain calls (host.call) instead of
  neighbor-table closures
- Build agent domain tools from the mount list and run the unified lifespan

Domains are added by dropping a directory with a module card into the domain
root — no code change here and none in agent/. Test-only wire kwargs go
through ``wire_extras`` (domain -> kwargs); this root does not know any
domain-specific hook names.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import os
from collections.abc import Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.app import AgentApp
from agent.build import EVENTS_RETENTION, build_agent
from agent.contracts import Purpose
from agent.llm import LLMClient
from agent.runtime.jobs_view import JobsView
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.settings import WORKSPACE_DIR_KEY
from fastapi import FastAPI
from platform_actor import LocalTokenIssuer
from platform_capability import CostQuota, SqliteAuditSink, Wiring
from platform_contracts import ErrorSuffix, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from .agent_rebuild import AgentRebuilder, _teardown_agent, build_switch_router
from .bridge import make_domain_tools
from .call import bind_calls
from .embedder_adapter import ServiceEmbedder
from .jobs_router import make_job_cancel_router
from .lifecycle import close_quietly, close_wirings, start_wirings, stop_wirings
from .llm_adapter import ServiceLLM
from .llm_routing import RoutingServiceLLM
from .plan import enabled_from_settings, register_gateway_settings, select_enabled, topo_order
from .scan import ServiceCard, scan
from .settings import DEFS as HOST_SETTING_DEFS

log = logging.getLogger("host.assemble")

ROOT = Path(__file__).resolve().parents[4]  # repo root (packages/host/src/host)

DOMAINS_DIR = "packages"
# Every domain is an installed top-level package (src layout), so a card's
# importable module is just its directory name: no parent-package prefix.
DOMAINS_MODULE_PREFIX = ""


def _load_env_file(path: Path) -> None:
    """Seed os.environ from the repo-root .env (KEY=VALUE lines, # comments).

    The composition root owns process assembly, so it also owns bringing the
    documented .env configuration (README: SECRETS_ENCRYPTION_KEY / SECRET_KEY)
    into the environment — no matter which launcher starts the process.
    Standard dotenv semantics: variables already set in the environment win.

    A malformed or unreadable file must never take the process down at import
    time: the same values can still arrive via the real environment, so the
    failure only warrants a warning.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        log.warning("skipping unreadable .env file %s: %s", path, exc)
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(ROOT / ".env")

# Keys a module card may declare in "needs". Each maps to a shared facility
# this root actually owns. Domain-specific test hooks (clone_fn, parse_fn, …)
# must NOT appear here: they travel through wire_extras so host stays
# domain-agnostic. A card that names an unknown key fails startup.
SHARED_KEYS = frozenset(
    {
        "bus",
        "secrets",
        "settings_store",
        "workspace",
        "audit",
        "quota",
        "call",
        "call_sync",
    }
)


@dataclass
class Backend:
    """Handle for the assembled artifacts; entry point for tests and debugging."""

    app: FastAPI
    agent: AgentApp
    wirings: dict[str, Wiring]
    bus: EventBus
    log: EventLog
    secrets: SecretStore
    settings_store: SettingsStore
    agent_rebuilder: Any = None  # restartless workspace-switch holder (None in tests not opting in)


def _resolve_workspace(
    workspace_dir: str | Path | None,
    settings_store: SettingsStore,
) -> Path:
    """Resolve the workspace directory: an explicit argument (test injection)
    wins; otherwise read agent.workspace.dir, resolving relative paths against
    the repo root and falling back to ROOT/data/workspace when empty/missing.
    Values from the settings store must stay inside the repo root.
    """
    if workspace_dir is not None:
        return Path(workspace_dir)
    raw = str(settings_store.get(WORKSPACE_DIR_KEY) or "").strip()
    if not raw:
        return ROOT / "data" / "workspace"
    if ".." in Path(raw).parts:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"agent.workspace.dir must not contain '..' segments: {raw}",
        )
    path = Path(raw)
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"agent.workspace.dir must stay inside the repo root: {raw}",
        )
    return path if path.is_absolute() else ROOT / path


def _int_setting(store: SettingsStore, key: str, default: int) -> int:
    try:
        raw = store.get(key)
        if raw is None or raw == "":
            return default
        return int(raw)
    except (TypeError, ValueError, ServiceError):
        log.warning("setting %s unreadable, using %s", key, default)
        return default


def _wire_card(
    card: ServiceCard,
    data_dir: Path,
    shared: Mapping[str, Any],
    extras: Mapping[str, Mapping[str, Any]],
) -> Wiring:
    """Load <module>.wiring.wire and call it with card.needs plus optional extras.

    The function signature of wire() is the contract: extras that wire() does
    not accept fail startup instead of being silently dropped.
    """
    module_name = f"{card.module}.wiring"
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"domain {card.domain} failed to load {module_name}: {exc}") from exc
    wire_fn = getattr(module, "wire", None)
    if not callable(wire_fn):
        raise TypeError(f"domain {card.domain} has no callable wire(): {module_name}")
    kwargs: dict[str, Any] = {"data_dir": data_dir}
    for key in card.needs:
        if key not in SHARED_KEYS:
            raise RuntimeError(
                f"domain {card.domain} needs declares an unknown key {key!r}"
                f" (available keys: {sorted(SHARED_KEYS)})"
            )
        kwargs[key] = shared[key]
    extra = dict(extras.get(card.domain) or {})
    if "data_dir" in extra:
        raise RuntimeError(f"wire_extras[{card.domain!r}] must not override data_dir")
    kwargs.update(extra)
    params = inspect.signature(wire_fn).parameters
    accepts_var_kw = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    unexpected = [k for k in kwargs if k not in params and not accepts_var_kw]
    if unexpected:
        raise RuntimeError(f"domain {card.domain} wire() does not accept arguments {unexpected}")
    try:
        return wire_fn(**kwargs)
    except TypeError as exc:
        raise RuntimeError(f"domain {card.domain} wire() call failed: {exc}") from exc


def _release_partial(
    *,
    wirings: Mapping[str, Wiring],
    agent: AgentApp | None,
    secrets: SecretStore,
    settings_store: SettingsStore,
    audit: list,
    event_log: EventLog,
) -> None:
    """Best-effort teardown when build() fails after opening facilities."""
    if agent is not None:
        close_quietly(agent, what="agent")
    close_wirings(list(wirings.values()))
    close_quietly(secrets, what="secrets")
    close_quietly(settings_store, what="settings_store")
    for i, sink in enumerate(audit):
        close_quietly(sink, what=f"audit[{i}]")
    close_quietly(event_log, what="event_log")


def build(
    data_dir: str | Path | None = None,
    workspace_dir: str | Path | None = None,
    *,
    llm: LLMClient | None = None,
    domains_root: str | Path | None = None,
    domains_prefix: str = DOMAINS_MODULE_PREFIX,
    wire_extras: Mapping[str, Mapping[str, Any]] | None = None,
) -> FastAPI:
    """Assemble the whole backend; run with uvicorn host.assemble:build --factory.

    llm: test injection (agent.llm.LLMClient); when omitted, ServiceLLM is used.
    domains_root / domains_prefix: test injection overriding the scanned root.
    wire_extras: optional {domain: kwargs} merged into that domain's wire()
    after needs injection. Host does not interpret the kwarg names.
    """
    from gateway.mounts import MountSpec
    from gateway.rest import create_app as gateway_create
    from gateway.uploads import build_upload_router
    from gateway.workspace import build_workspace_router

    data_root = Path(data_dir) if data_dir else ROOT / "data/runtime"
    data_root.mkdir(parents=True, exist_ok=True)

    event_log = EventLog(data_root / "events.db", retention=EVENTS_RETENTION)
    bus = EventBus(event_log)
    secrets = SecretStore(data_root / "secrets.db")
    settings_store = SettingsStore(data_root / "settings.db", bus)
    audit = [SqliteAuditSink(data_root / "audit.db")]
    issuer = LocalTokenIssuer(data_root / "machine.token")
    quota = [CostQuota(default_daily_budget=50_000)]
    wirings: dict[str, Wiring] = {}
    agent: AgentApp | None = None
    try:
        settings_store.register_fresh(AGENT_SETTING_DEFS)
        settings_store.register_fresh(HOST_SETTING_DEFS)
        cards = scan(
            domains_root if domains_root is not None else ROOT / DOMAINS_DIR,
            domains_prefix,
        )
        register_gateway_settings(cards, settings_store)
        workspace = _resolve_workspace(workspace_dir, settings_store)
        ordered = topo_order(
            select_enabled(
                cards,
                enabled_names=enabled_from_settings(settings_store),
            )
        )
        extras = {k: dict(v) for k, v in dict(wire_extras or {}).items()}
        unknown_extras = set(extras) - {c.domain for c in ordered}
        if unknown_extras:
            raise RuntimeError(f"wire_extras references unwired domains: {sorted(unknown_extras)}")
        call, call_sync = bind_calls(wirings, audit=audit, quota=quota)
        shared: dict[str, Any] = {
            "bus": bus,
            "secrets": secrets,
            "settings_store": settings_store,
            "workspace": workspace,
            "audit": audit,
            "quota": quota,
            "call": call,
            "call_sync": call_sync,
        }
        for card in ordered:
            wirings[card.domain] = _wire_card(
                card,
                data_root / card.domain,
                shared,
                extras,
            )
        mounts = [
            MountSpec(domain=name, registry=w.registry, probe=w.probe, extra_router=w.extra_router)
            for name, w in wirings.items()
        ]
        extra_routers = [
            build_upload_router(workspace),
            build_workspace_router(workspace),
            build_switch_router(),
        ]
        agent = build_agent(
            data_dir=data_root / "agent",
            workspace_dir=workspace,
            llm=llm if llm is not None else ServiceLLM(call),
            bus=bus,
            settings_store=settings_store,
            extra_tools=make_domain_tools(mounts, audit=audit, quota=quota),
            job_cancel=make_job_cancel_router(call, JobsView(event_log)),
            audit=audit,  # the agent's own governance tools audit as actor=agent into the same sinks
            embedder=ServiceEmbedder(call_sync, settings_store),  # vector recall via llm.embed
            # Purpose routing (phase 18): arbiter/distill/planner transports read
            # agent.llm.routing and fall back along the chain; unpurposed calls
            # stay on the default chat model
            purpose_llms={
                purpose.value: RoutingServiceLLM(
                    call, purpose=purpose, settings=settings_store, bus=bus
                )
                for purpose in (Purpose.ARBITER, Purpose.DISTILL, Purpose.CONTEXT_PLANNER)
            },
        )
        built = agent
        mounts.append(
            MountSpec(
                domain="agent",
                registry=built.registry,
                probe=lambda: {"status": "up"},
            )
        )
        # Restartless workspace switching: the holder owns everything a new
        # agent generation needs plus the live generation's task handles, all
        # rotated under one lock (see host.agent_rebuild). domain_mounts is
        # snapshotted before the agent mount above so a rebuild never feeds
        # the agent's own registry back into its domain tools.
        rebuilder = AgentRebuilder(
            root=ROOT,
            data_agent_dir=data_root / "agent",
            bus=bus,
            event_log=event_log,
            settings_store=settings_store,
            domain_mounts=[m for m in mounts if m.domain != "agent"],
            call=call,
            call_sync=call_sync,
            audit=audit,
            quota=quota,
            issuer=issuer,
            injected_llm=llm,
            agent=built,
            current_workspace=workspace,
        )

        @asynccontextmanager
        async def lifespan(_app: FastAPI):
            async with rebuilder.lock:
                try:
                    await start_wirings(wirings)
                    rebuilder.mcp_task = asyncio.create_task(built.mcp.start())
                    rebuilder.agent_task = asyncio.create_task(built.loop.run())
                    with suppress(Exception):
                        await built.start_queue_loop()
                except BaseException:
                    await _teardown_agent(built, rebuilder.agent_task, rebuilder.mcp_task)
                    rebuilder.agent_task = None
                    rebuilder.mcp_task = None
                    rebuilder.agent = None
                    rebuilder.current_workspace = None
                    await stop_wirings(list(wirings.values()))
                    close_wirings(list(wirings.values()))
                    close_quietly(built, what="agent")
                    close_quietly(secrets, what="secrets")
                    close_quietly(settings_store, what="settings_store")
                    for i, sink in enumerate(audit):
                        close_quietly(sink, what=f"audit[{i}]")
                    close_quietly(event_log, what="event_log")
                    raise
            try:
                yield
            finally:
                # Shutdown tears down the CURRENT generation (a workspace
                # switch may have replaced the startup one), serialized with
                # concurrent switches.
                async with rebuilder.lock:
                    current = rebuilder.agent
                    agent_task = rebuilder.agent_task
                    mcp_task = rebuilder.mcp_task
                    rebuilder.agent = None
                    rebuilder.agent_task = None
                    rebuilder.mcp_task = None
                    rebuilder.current_workspace = None
                    if current is not None:
                        await _teardown_agent(current, agent_task, mcp_task)
                    await stop_wirings(list(wirings.values()))
                    close_wirings(list(wirings.values()))
                    if current is not None:
                        close_quietly(current, what="agent")
                    close_quietly(secrets, what="secrets")
                    close_quietly(settings_store, what="settings_store")
                    for i, sink in enumerate(audit):
                        close_quietly(sink, what=f"audit[{i}]")
                    close_quietly(event_log, what="event_log")

        app = gateway_create(
            mounts,
            bus=bus,
            lifespan=lifespan,
            issuer=issuer,
            quota=quota,
            audit=audit,
            extra_routers=extra_routers,
            trajectory=built.trajectory,  # /api/chat/trajectory reads the projection, not the log
            rate_limit_per_minute=_int_setting(
                settings_store, "gateway.rate_limit.per_minute", 600
            ),
            sse_max_connections=_int_setting(settings_store, "gateway.sse.max_connections", 8),
            history_page_size=_int_setting(settings_store, "gateway.chat.history_page_size", 200),
        )
        app.state.backend = Backend(
            app=app,
            agent=built,
            wirings=wirings,
            bus=bus,
            log=event_log,
            secrets=secrets,
            settings_store=settings_store,
            agent_rebuilder=rebuilder,
        )
        app.state.agent_rebuilder = rebuilder
        return app
    except BaseException:
        _release_partial(
            wirings=wirings,
            agent=agent,
            secrets=secrets,
            settings_store=settings_store,
            audit=audit,
            event_log=event_log,
        )
        raise
