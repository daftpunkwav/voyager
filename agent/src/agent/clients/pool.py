"""MCP client connection pool: external MCP servers added and approved by
the user in settings.

In the monolith, domain tools already enter the tool surface via the
host.bridge capability bridge, so the pool must never ingest the
packages/*/mcp_server set again; it only holds user-added, user-approved
stdio/URL MCP servers. An empty pool is a legitimate steady state.

Boundary: validation/connection here; mounting in mount.py. Config
persistence uses the agent.mcp.servers setting; writes go through this pool
with an actor passed by the capabilities/mcp.py capability (landed in
audit). Tests inject connect=... with fake sessions (no processes, no
network); production uses session.default_connect.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

from agent.clients.mount import remount, unmount
from agent.clients.session import McpSession, default_connect
from agent.tools.core.base import Toolbelt

#: Settings key: external MCP config list
MCP_KEY = "agent.mcp.servers"

#: Legal shape of a config id (stable primary key, feeds tool name mcp__<id>__<tool>)
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")

CONNECT_TIMEOUT = 15.0  # cap for connection handshake + tools/list (seconds)

ConnectFn = Callable[[dict], Awaitable[McpSession]]

log = logging.getLogger("agent.mcp")


def validate_server_config(raw: dict) -> dict:
    """Validate and normalize one external MCP config; failures raise
    AGENT.INVALID_INPUT, never silently dropped."""
    if not isinstance(raw, dict):
        raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "MCP config must be an object")
    sid = str(raw.get("id") or "").strip()
    if not _ID_RE.match(sid):
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"id must start with a lowercase letter, 1-32 chars of lowercase letters/digits/hyphens: {sid!r}",
        )
    name = str(raw.get("name") or "").strip() or sid
    kind = raw.get("kind")
    approval = raw.get("approval") or "item"
    if kind not in ("stdio", "url"):
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT, f"kind must be stdio or url: {kind!r}"
        )
    if approval not in ("package", "item"):
        raise ServiceError(
            "agent", ErrorSuffix.INVALID_INPUT, f"approval must be package or item: {approval!r}"
        )
    args = [str(a) for a in (raw.get("args") or [])]
    command = str(raw.get("command") or "").strip()
    url = str(raw.get("url") or "").strip()
    if kind == "stdio":
        if not command:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, "command must not be empty for stdio"
            )
        url = ""
    else:
        if not (url.startswith(("http://", "https://"))):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"url must start with http:// or https:// (file: forbidden): {url!r}",
            )
        command, args = "", []
    return {
        "id": sid,
        "name": name,
        "kind": kind,
        "command": command,
        "args": args,
        "url": url,
        "approval": approval,
        "enabled": bool(raw.get("enabled", True)),
    }


class McpClientPool:
    """External MCP server connection pool: connect (injectable) -> preview ->
    approve -> mount into the root Toolbelt."""

    def __init__(
        self,
        *,
        settings: Any = None,  # SettingsStore: reads/writes agent.mcp.servers
        toolbelt: Toolbelt | None = None,  # root registry: register into it after approval
        connect: ConnectFn | None = None,  # test injection; defaults to session.default_connect
        cwd: str | Path | None = None,  # stdio subprocess working directory (= agent workdir)
    ) -> None:
        self._settings = settings
        self._toolbelt = toolbelt
        self._connect = connect or default_connect
        self._cwd = str(cwd) if cwd else None
        self._sessions: dict[str, McpSession] = {}
        self._previews: dict[str, list[dict]] = {}  # latest tools/list per server
        self._errors: dict[str, str] = {}  # per-entry error from the last failed start/reconnect
        self._started = False
        self._close_tasks: set[asyncio.Task] = set()  # keeps close_best_effort tasks referenced
        self._connect_lock = (
            asyncio.Lock()
        )  # serialize connects per server: concurrent previews must not leak duplicate connections

    # ---- Config (agent.mcp.servers; writes land in audit via actor) ----

    def configs(self) -> list[dict]:
        if self._settings is None:
            return []
        return [dict(c) for c in (self._settings.get(MCP_KEY) or [])]

    def find_config(self, sid: str) -> dict | None:
        return next((c for c in self.configs() if c.get("id") == sid), None)

    async def _save_configs(self, configs: list[dict], actor: Any) -> None:
        if self._settings is None:
            raise ServiceError(
                "agent", ErrorSuffix.INTERNAL, "MCP pool has no settings store bound"
            )
        await self._settings.set(MCP_KEY, configs, actor)

    async def upsert_config(self, cfg: dict, actor: Any) -> None:
        """Replace one whole entry (matched by id); other entries untouched."""
        configs = [c for c in self.configs() if c.get("id") != cfg["id"]]
        configs.append(cfg)
        await self._save_configs(configs, actor)

    async def delete_config(self, sid: str, actor: Any) -> None:
        await self._save_configs([c for c in self.configs() if c.get("id") != sid], actor)

    # ---- Connect and preview ----

    async def preview(self, sid: str) -> list[dict]:
        """Connect (if not yet) and run tools/list, returning the remote tool
        list.

        validate_server_config runs before connecting: a dirty config (left
        over from settings written directly, bypassing add validation) is
        recorded as the entry's error and refused, never passed to connect.
        Other failures raise AGENT.UNAVAILABLE (readable message) and are also
        recorded in the entry state; the config itself is untouched, so the
        user can preview again after fixing the environment.
        """
        cfg = self.find_config(sid)
        if cfg is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such external MCP: {sid}")
        try:
            validate_server_config(cfg)
        except ServiceError as exc:
            self._errors[sid] = str(exc)
            raise
        try:
            # Hold the pool-level lock for the connect section: concurrent
            # previews of the same server reuse the first connection instead of
            # each building one and leaking the other
            async with self._connect_lock:
                if sid not in self._sessions:
                    self._sessions[sid] = await asyncio.wait_for(
                        self._connect({**cfg, "cwd": self._cwd}), CONNECT_TIMEOUT
                    )
                tools = await asyncio.wait_for(
                    self._sessions[sid].list_remote_tools(), CONNECT_TIMEOUT
                )
        except Exception as exc:  # timeouts included: uniform readable error, no exception leaks past the capability frame
            await self.drop_session(sid)
            message = f"MCP '{cfg['name']}' failed to connect or list tools: {exc}"
            self._errors[sid] = message
            raise ServiceError("agent", ErrorSuffix.UNAVAILABLE, message) from exc
        self._previews[sid] = tools
        self._errors.pop(sid, None)
        # Already approved: a successful tools/list remounts (so a server fixed
        # after a failed startup rejoins the tool surface via "refresh")
        approved = list(cfg.get("approved") or [])
        if approved:
            self.remount(sid, approved)
        return tools

    async def drop_session(self, sid: str) -> None:
        """Disconnect and drop one server's session; no-op when not connected."""
        session = self._sessions.pop(sid, None)
        if session is not None:
            try:
                await session.aclose()
            except Exception:  # cleanup path: best-effort disconnect, never blocks the caller
                log.warning("failed to disconnect MCP session: %s", sid, exc_info=True)

    # ---- Mounting (into the Toolbelt surface; implementation in mount.py) ----

    def remount(self, sid: str, approved: list[str]) -> list[str]:
        """Mount per the approved list (["*"] = everything from preview); the old
        mount is removed first so stale names cannot linger.

        Requires a preview to be present (call preview() first); returns the
        tool names mounted this time.
        """
        session = self._sessions.get(sid)
        remote_tools = self._previews.get(sid) or []
        cfg = self.find_config(sid) or {"id": sid, "name": sid}
        return remount(self._toolbelt, cfg, session, remote_tools, approved)

    def unmount(self, sid: str) -> list[str]:
        """Unmount mcp__<sid>__* from the root registry; returns the names
        actually removed."""
        return unmount(self._toolbelt, sid)

    # ---- Lifecycle ----

    async def start(self) -> None:
        """Startup reconnect (called from the composition root lifespan): connect and mount
        entries that are enabled and approved.

        Idempotent (repeat calls are no-ops); a per-server failure is recorded
        in the entry error and blocks neither startup nor other servers; dirty
        entries without an id (direct settings writes) are skipped the same way.
        """
        if self._started:
            return
        self._started = True
        for cfg in self.configs():
            if not cfg.get("enabled", True) or not cfg.get("approved"):
                continue
            sid = str(cfg.get("id") or "").strip()
            if not sid:
                continue
            try:
                # preview remounts on its own when already approved
                await self.preview(sid)
            except Exception as exc:  # noqa: BLE001  # per-server failure recorded for the settings page; startup continues
                self._errors[sid] = str(exc)

    def list_state(self) -> list[dict]:
        """Settings-page data source: config + runtime state (connected / error /
        preview / mounted).

        Dirty entries without an id are skipped so one KeyError cannot break
        the settings list API.
        """
        mounted_all = self._toolbelt.names() if self._toolbelt else []
        return [
            {
                **cfg,
                "connected": sid in self._sessions,
                "error": self._errors.get(sid, ""),
                "preview": self._previews.get(sid, []),
                "mounted": [n for n in mounted_all if n.startswith(f"mcp__{sid}__")],
            }
            for cfg in self.configs()
            if (sid := str(cfg.get("id") or "").strip())
        ]

    async def aclose_sessions(self, sessions: list[McpSession] | None = None) -> None:
        targets = list(self._sessions.values()) if sessions is None else sessions
        for session in targets:
            try:
                await session.aclose()
            except Exception:  # shutdown cleanup: best-effort disconnect, other sessions proceed
                log.warning("failed to disconnect MCP session during shutdown", exc_info=True)
        if sessions is None:
            self._sessions.clear()

    def close_best_effort(self) -> None:
        """Sync shutdown for AgentApp.close: schedule a task when a loop is
        running; otherwise kill synchronously on a best-effort basis."""
        sessions = list(self._sessions.values())
        self._sessions.clear()
        if not sessions:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            for session in sessions:
                closer = getattr(session, "close_sync", None)
                if closer is not None:
                    try:
                        closer()
                    except Exception:  # best-effort sync kill (logging may already be gone)
                        log.warning(
                            "failed to kill MCP session during sync shutdown", exc_info=True
                        )
        else:
            # Hold a reference to prevent premature GC: if the shutdown task is
            # collected, stdio MCP sessions never close and the error stays silent
            task = loop.create_task(self.aclose_sessions(sessions))
            self._close_tasks.add(task)
            task.add_done_callback(self._close_tasks.discard)
