"""AgentApp: the assembly product holding handles to every in-process
component (shared by tests, main, and the host composition root).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

from agent.clients import McpClientPool
from agent.context import PageContextRegistry
from agent.hooks import HookRegistry, UserHookReloader
from agent.master import Master
from agent.memory import Memory
from agent.plugins import PluginManager
from agent.runtime import EventLoop, Meter
from agent.skills import SkillLoader
from agent.subagent import Spawner
from agent.tools import AskUser


@dataclass
class AgentApp:
    """Assembly product: handles to every in-process component (shared by
    tests and main)."""

    bus: EventBus
    log: EventLog
    settings: SettingsStore
    memory: Memory
    master: Master
    loop: EventLoop
    skills: SkillLoader
    hooks: HookRegistry
    pages: PageContextRegistry
    asker: AskUser
    spawner: Spawner
    registry: Any  # agent capability registry (capabilities.registry)
    mcp: McpClientPool  # external MCP connection pool (empty pool is legal)
    meter: Meter  # in-memory metering (resource dimension; shared by metered_llm and the quota-query capability)
    plugins: PluginManager  # plugin discovery and bundle approval
    user_hooks: UserHookReloader  # hot load/unload of user workspace/hooks
    session_store: Any  # SessionStore: chat persistence (closed with the app)
    trajectory: Any  # TrajectoryStore: query projection over the event log (closed with the app)
    queue_store: Any  # QueueStore: durable delayed/cron jobs (closed with the app)
    scheduler: Any  # Scheduler: concurrency cap, timers, durable-job poll loop
    checkpoints: Any  # CheckpointStore: run snapshots (resume/abandon paths)
    approvals: Any  # ApprovalStore: remembered L2 grants (closed with the app)
    write_journal: Any = (
        None  # WriteJournal: fs write backups for undo_writes (closed with the app)
    )
    owns_settings: bool = (
        True  # False when sharing a store (aggregate runs); close() leaves it open
    )
    owns_log: bool = True  # False when sharing a bus (aggregate runs share the EventLog)
    session_index: Any = None  # SessionIndex: FTS search projection (closed with the app; optional for legacy constructors)
    dispatcher: Any = None  # TraceDispatcher: span exporter lifecycle (flushed in drain, detached in close)

    async def start_queue_loop(self, *, poll_interval: float = 5.0) -> None:
        """Start the durable-job poll loop (host lifespan; needs a running loop)."""
        await self.scheduler.start_queue(self.queue_store, poll_interval=poll_interval)

    async def drain(self, timeout: float = 5.0) -> None:
        """Wait for in-flight chat turns (master background tasks) to finish.

        Shutdown ordering: stores must not close while a turn's worker threads
        may still write — a sqlite use-after-close is a hard crash, not an
        exception. The EventLoop task is cancelled before draining, so no new
        turns start; a stuck turn is cancelled after the grace timeout (best
        effort: shutdown must always terminate)."""
        import asyncio

        if self.dispatcher is not None:
            try:
                await self.dispatcher.flush()
            except Exception:  # noqa: BLE001, S110  # best effort: dispatcher flush failure ignored on drain
                pass
        bg = getattr(self.master, "_bg", None)
        pending = [t for t in tuple(bg) if not t.done()] if bg else []
        if not pending:
            return
        _done, still = await asyncio.wait(pending, timeout=timeout)
        for task in still:
            task.cancel()

    def close(self) -> None:
        """Close components holding file handles (tests and shutdown paths)."""
        # External MCP sessions: schedule an aclose task when a loop exists,
        # otherwise a best-effort synchronous kill (never blocks pytest)
        if self.dispatcher is not None:
            self.dispatcher.detach()
        self.mcp.close_best_effort()
        self.meter.close()  # meter.db persistent connection; in-memory Meter is a no-op
        self.memory.close()
        self.session_store.close()
        self.trajectory.close()
        if self.session_index is not None:
            self.session_index.close()
        self.queue_store.close()
        self.approvals.close()
        if self.write_journal is not None:
            self.write_journal.close()
        if self.owns_settings:
            self.settings.close()
        if self.owns_log:
            self.log.close()


__all__ = ["AgentApp"]
