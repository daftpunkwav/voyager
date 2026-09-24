"""build_agent(): the agent composition root — the single source of the
assembly order.

Assembles every component into the shared AgentApp (bus / log / settings /
memory / master / loop / skills / hooks / pages / asker / spawner /
capability registry / mcp pool / meter / plugins / user-hook reloader) and
registers the built-in tools; tools that bind the master (spawn_subagent,
session and governance tools) are registered after the master exists.
Also used by tests (injected FakeLLM / temp directories).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from platform_contracts import DomainEvent, ServiceError
from platform_eventbus import CursorStore, EventBus, EventLog, Retention
from platform_settings import SettingsStore

from agent.app import AgentApp
from agent.capabilities import CapabilityDeps, build_agent_registry
from agent.clients import McpClientPool
from agent.clients.pool import ConnectFn
from agent.context import ContextBuilder, OnDemandLoader, PageContextRegistry
from agent.context.budgets import budget_from_settings
from agent.context.plan_gate import PlanGates
from agent.context.rules import GLOBAL_RULES
from agent.context.scoped_rules import ScopedRules
from agent.hooks import HookLoader, HookRegistry, UserHookReloader
from agent.llm import FakeLLM, LLMClient
from agent.master import Arbiter, DigestStore, Master
from agent.master.blackboard import Blackboard
from agent.master.goal import GoalManager
from agent.master.goal_driver import GoalDriver
from agent.master.job_notify import JobNotifier
from agent.master.outreach_budget import OutreachBudget
from agent.master.proactive import ProactiveEngine
from agent.master.task_board import TaskBoard
from agent.master.task_graph import TaskGraph
from agent.memory import Memory
from agent.memory.distill import Distiller
from agent.memory.read_policy import render_relevant_recall
from agent.memory.recorder import EpisodeRecorder
from agent.memory.session_store import SessionStore
from agent.personas import canonical_persona_key, resolve_persona
from agent.plugins import PluginManager
from agent.policy import AppPolicy, FsPolicy, NetworkPolicy, PolicyEngine
from agent.policy.permissions import ToolPermissions
from agent.runtime import (
    EventLoop,
    LangfuseSpanExporter,
    Meter,
    MeterStore,
    OtlpHttpSpanExporter,
    RuntimeEvents,
    Scheduler,
    TraceDispatcher,
    metered_llm,
    output_capped_llm,
)
from agent.runtime.jobs_view import JobsView
from agent.runtime.queue_store import QueueStore
from agent.runtime.session_index import SessionIndex
from agent.runtime.state import CheckpointStore, prepare_resumable_checkpoints
from agent.runtime.trajectory import TrajectoryStore
from agent.runtime.wake_budget import WakeBudget
from agent.runtime.wire import bind_event_loop
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.settings import STYLE_OVERRIDES_KEY, WORKSPACE_DIR_KEY
from agent.skills import SkillLoader
from agent.skills.organizer import SkillOrganizer
from agent.subagent import Spawner, SubagentRegistry
from agent.subagent.triggered_spawn import make_handler as make_trigger_handler
from agent.subagent.triggered_spawn import trigger_patterns
from agent.tools import (
    AgentTool,
    AskUser,
    Question,
    StaticToolSource,
    TodoStore,
    Toolbelt,
    ToolRegistry,
    ask_user_tool,
    context_tools,
    ensure_workdir,
    extension_tools,
    fs_tools,
    jobs_tools,
    memory_tools,
    observe_tools,
    plan_tools,
    request_context_tool,
    scratchpad_tool,
    search_tools,
    session_tools,
    shell_tools,
    skill_tools,
    team_tools,
    todo_tools,
    tools_tools,
    web_tools,
)
from agent.tools.core.result_budget import MAX_AGE_SECONDS, bound_spill_dir, spill_result
from agent.tools.core.self_capability import AuditSinks
from agent.tools.workspace.write_journal import WriteJournal

#: Retention for the shared event log: streaming deltas (one row per text
#: chunk) are an ephemeral display stream - keep them for a day so brief SSE
#: reconnects can replay, then reclaim the rows; message-level events are
#: never purged. Defined here because both assembly roots (standalone agent
#: and host aggregate) construct the log, and agent.delta is an agent-owned
#: event type (review F-103).
EVENTS_RETENTION = Retention(types=(DomainEvent.AGENT_DELTA,), max_age_s=24 * 3600.0)

#: Raw LLM round log retention (days): full request/response bodies per
#: round are the largest unbounded artifact in the runtime data directory.
RAW_LOG_RETENTION_DAYS = 7


def _build_policy(
    settings: SettingsStore, workspace: Path
) -> tuple[PolicyEngine, tuple[str, ...], tuple[str, ...]]:
    """Policy engine: returns (policy, read_roots, write_roots).

    Roots are fixed at assembly time (workspace is not hot-swappable); the
    network/app/fs (additional read roots) dimensions hot-read via the
    settings handle, so setting changes apply without a restart. read/write
    roots also seed the fs tool layer's initial registry (double-layer
    defense).
    """
    read_roots = tuple(settings.get("agent.fs.read_roots") or ())
    write_roots = tuple(settings.get("agent.fs.write_roots") or ())
    policy = PolicyEngine(
        network=NetworkPolicy(
            mode=settings.get("agent.network.mode"),
            domains=tuple(settings.get("agent.network.domains")),
        ),
        fs=FsPolicy(roots=(str(workspace),), read_roots=read_roots, write_roots=write_roots),
        app=AppPolicy(
            allowed=frozenset(settings.get("agent.app.allowed")),
            denied=frozenset(settings.get("agent.app.denied")),
        ),
        settings=settings,
    )
    return policy, read_roots, write_roots


def _build_tools(
    settings: SettingsStore,
    workspace: Path,
    policy: PolicyEngine,
    on_demand: OnDemandLoader,
    asker: AskUser,
    read_roots: tuple[str, ...],
    write_roots: tuple[str, ...],
    provide_context: Any,
    write_journal: Any = None,
    extra_tools: dict[str, AgentTool] | None = None,
) -> ToolRegistry:
    """Assemble the builtin tool roster through named sources.

    Merge order (later wins on clashes) matches the previous dict.update
    chain exactly: fs / search / shell / web / interact / memory / plan,
    then the injected domain bridge. spawn_subagent is not here - it needs
    to call back into master.dispatch_task, so build_agent registers it
    after the master is assembled via toolbelt.register.
    """
    roots: list[str | Path] = [workspace]
    read_root_list: list[str | Path] = list(read_roots)
    write_root_list: list[str | Path] = list(write_roots)

    def _read_roots_fn() -> list[str | Path]:
        return list(settings.get("agent.fs.read_roots") or ())

    def _write_roots_fn() -> list[str | Path]:
        return list(settings.get("agent.fs.write_roots") or ())

    registry = ToolRegistry()
    registry.add(
        StaticToolSource(
            "fs",
            fs_tools(
                roots,
                read_root_list,
                write_root_list,
                read_roots_fn=_read_roots_fn,
                write_roots_fn=_write_roots_fn,
                journal=write_journal,
            ),
        )
    )
    registry.add(
        StaticToolSource(
            "search",
            search_tools(
                roots,
                read_root_list,
                write_root_list,
                read_roots_fn=_read_roots_fn,
                write_roots_fn=_write_roots_fn,
            ),
        )
    )
    registry.add(StaticToolSource("shell", shell_tools(workspace)))
    registry.add(StaticToolSource("web", web_tools(policy)))
    ask = ask_user_tool(asker)
    req = request_context_tool(provide_context)
    registry.add(StaticToolSource("interact", {ask.name: ask, req.name: req}))
    registry.add(StaticToolSource("skill", skill_tools(on_demand, workspace / "skills")))
    # Plan/todos + scratchpad: persisted under the workspace; the plan file is
    # resolved per executing session (todos/<session>.json, global todo.json
    # for session-less work), the scratchpad is shared across turns/instances
    scratchpad = scratchpad_tool(workspace)
    registry.add(
        StaticToolSource(
            "plan",
            {**todo_tools(TodoStore(workspace / "todo.json")), scratchpad.name: scratchpad},
        )
    )
    # LLM-driven context management: status + proactive compaction (resolve
    # the executing instance via the current_instance ContextVar)
    registry.add(StaticToolSource("context", context_tools()))
    registry.add(
        StaticToolSource("domain", extra_tools or {})
    )  # domain capability bridge (injected for aggregate runs)
    return registry


def build_agent(
    *,
    data_dir: str | Path = "data/runtime",
    workspace_dir: str | Path | None = None,
    llm: LLMClient | None = None,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
    extra_tools: dict[str, AgentTool] | None = None,
    mcp_connect: ConnectFn | None = None,  # external MCP connect injection (test fakes)
    plugins_dir: str
    | Path
    | None = None,  # plugin root (default repo plugins/; tests inject a temp dir)
    audit: AuditSinks | None = None,  # audit sinks shared with the human REST projection (host)
    embedder: Any | None = None,  # memory.vector.EmbeddingFn (host injects the llm embed adapter)
    purpose_llms: dict[str, LLMClient]
    | None = None,  # per-purpose transports (host injects RoutingServiceLLM); absent -> chat llm
    job_cancel: Any | None = None,  # async (job_id) -> dict, host-routed to the source domain
    job_reorder: Any
    | None = None,  # async (job_id, priority) -> dict, host-routed to the source domain
) -> AgentApp:
    data_dir = Path(data_dir)
    if llm is None:
        # No-key degradation: still runnable, but the operator must know they
        # are on a fake LLM
        logging.getLogger("agent.main").warning(
            "no LLM injected; degrading to FakeLLM (stub, replies are placeholder text);"
            " inject a real LLM via packages/host assembly for aggregate runs"
        )
        llm = FakeLLM()
    owns_log = bus is None

    log = EventLog(data_dir / "events.db", retention=EVENTS_RETENTION)
    bus = bus or EventBus(log)
    if not owns_log:
        # The bus was injected by the host: it persists into the host's own
        # shared log, and the local file above would stay empty forever.
        # Projections (trajectory, session index) must read the log the bus
        # actually writes to, or every step is lost across restarts.
        log = bus.log
    cursors = CursorStore(log.conn, log.lock)

    owns_settings = settings_store is None
    settings = settings_store or SettingsStore(data_dir / "settings.db", bus=bus)
    settings.register_fresh(AGENT_SETTING_DEFS)  # idempotent: only registers missing agent.* keys

    workspace = ensure_workdir(workspace_dir or settings.get(WORKSPACE_DIR_KEY))
    memory = Memory(data_dir / "memory", embedder=embedder)
    pages = PageContextRegistry()
    asker = AskUser(bus)
    plan_gates = PlanGates()  # session review-phase state (human-toggled, in-memory)
    # Skill roots: built-in + user skills dir; unapproved plugin skills never enter the index
    skills_dir = workspace / "skills"  # the agent's home, created at assembly time
    skills_dir.mkdir(parents=True, exist_ok=True)
    skills = SkillLoader([Path(__file__).parent / "skills" / "builtin", skills_dir])
    # Hooks: declarative hooks from the user hooks directory take effect directly;
    # the plugin directory is not loaded here
    # Hooks are user/plugin code: every execution lands in the same audit
    # chain as capability calls (fan-out over the shared sink list)
    hook_audit = (
        (lambda entry: [sink.record(entry) for sink in audit]) if audit is not None else None
    )
    hooks = HookRegistry(auditor=hook_audit)
    HookLoader(hooks).load_dir(workspace / "hooks", source="user", approved=True)
    digests = DigestStore()
    on_demand = OnDemandLoader(skills=skills, memory=memory, pages=pages)

    # Additional read roots + additional write roots: both the policy engine and
    # the fs tool layer jail must allow them (double-layer defense; write/delete
    # on write_roots goes through policy's L2 confirmation)
    policy, read_roots, write_roots = _build_policy(settings, workspace)
    meter_store = MeterStore(data_dir / "meter.db")
    # Startup library maintenance: purge daily rows older than 90 days so
    # meter.db does not grow with dates
    meter_store.purge_older_than_days(90)
    meter = Meter(
        store=meter_store,
        pricing_overrides_fn=lambda: settings.get("agent.pricing.overrides"),
    )

    # Daily token quota (resource dimension): the main conversation, dispatches,
    # and the arbitration judge all go through the same
    # metered_llm wrapper, hot-reading agent.resource.daily_tokens before each
    # complete; once the daily total exceeds the cap no real call is made
    # (0 = unlimited).
    def _metered(client: LLMClient) -> LLMClient:
        return metered_llm(
            client, meter, quota_fn=lambda: settings.get("agent.resource.daily_tokens") or 0
        )

    # Wire max_tokens: inject the configured per-model output budget into
    # every call (agent.context.max_output_tokens + model_profiles) so the
    # request honors user settings instead of the transport's built-in
    # default. Innermost, so the quota gate still sees the original shape.
    def _capped(client: LLMClient) -> LLMClient:
        return output_capped_llm(client, settings)

    chat_llm = _metered(_capped(llm))
    # Purpose routing (phase 18): arbiter, distillation, and the context
    # editor's planning call may run on lighter models resolved by the host
    # routing layer; without an injected transport everything shares the chat
    # model as before
    routes = purpose_llms or {}

    def _confirm_timeout_s() -> float:
        """Confirmation dialog timeout derived from the live tool deadline.

        Must stay below agent.execution.tool_deadline_s so the dialog cannot
        outlive the call it guards; a 15 s headroom keeps network/queue lag
        from causing a race, and a 10 s floor keeps very short deadlines
        usable for quick smoke tests."""
        try:
            tool_s = float(settings.get("agent.execution.tool_deadline_s"))
        except (TypeError, ValueError, ServiceError):  # unregistered reads NOT_FOUND
            tool_s = 90.0
        if tool_s <= 0:
            tool_s = 90.0
        return max(10.0, tool_s - 15.0)

    arbiter_llm = _metered(_capped(routes["arbiter"])) if "arbiter" in routes else chat_llm
    distiller_llm = _metered(_capped(routes["distill"])) if "distill" in routes else chat_llm
    planner_llm = (
        _metered(_capped(routes["context_planner"])) if "context_planner" in routes else chat_llm
    )
    events = RuntimeEvents(bus)

    async def _confirm(prompt: str) -> bool:
        """L2 confirmation via asking the user; no answer before timeout means
        declined. The question timeout is derived from the live tool deadline
        so the dialog never outlives the call it guards."""
        answer = await asker.ask(
            Question(prompt=prompt, kind="confirm", timeout_s=_confirm_timeout_s())
        )
        return bool(answer)

    async def _notify(message: str) -> None:
        """L1 permission notice: pushed to the Chat toast via the event stream,
        never posing as conversation."""
        await events.emit(DomainEvent.AGENT_POLICY_NOTIFY, message=message)

    def _provide_context(need: str) -> dict[str, str]:
        """Master side of request_context: summaries only, never full context."""
        return {"need": need, "profile": memory.profile.render(), "subagents": digests.render()}

    # Write journal: content-addressed backups behind the fs write tools
    # (checkpoint/audit support); lives under data_dir, outside the workspace jail
    write_journal = WriteJournal(data_dir / "write_journal")
    tool_registry = _build_tools(
        settings,
        workspace,
        policy,
        on_demand,
        asker,
        read_roots,
        write_roots,
        _provide_context,
        write_journal=write_journal,
        extra_tools=extra_tools,
    )
    tools = tool_registry.build()
    # Roster introspection is a live consumer of origins(): which layer owns
    # each tool, visible in startup logs for assembly diagnosis.
    _counts: dict[str, int] = {}
    for _source in tool_registry.origins().values():
        _counts[_source] = _counts.get(_source, 0) + 1
    logging.getLogger("agent.main").info(
        "tool roster: %d tools from %s",
        len(tools),
        ", ".join(f"{name}({_counts.get(name, 0)})" for name in tool_registry.source_names()),
    )

    def _spill_result(result: str, tool: str) -> str:
        """Oversized tool-result budget: truncate to a preview and spill the
        full output under workspace/spill/ (read_file can pull it back); the
        dual dimensions (chars/lines) hot-read settings, 0 disables. The
        spill directory is bounded on every call (missing dir is a no-op),
        not only when this result spilled, so old files cannot linger while
        later results stay small."""
        limit = int(settings.get("agent.context.tool_result_max") or 0)
        max_lines = int(settings.get("agent.context.tool_result_max_lines") or 0)
        text = spill_result(
            result,
            tool=tool,
            spill_dir=workspace / "spill",
            limit=limit,
            max_lines=max_lines,
        )
        bound_spill_dir(workspace / "spill", max_age_s=MAX_AGE_SECONDS)
        return text

    # spawn_subagent is not assembled here: it calls back into
    # master.dispatch_task while the master depends on this toolbelt - so it is
    # registered after the master is constructed (no placeholder-dict mutual refs)
    toolbelt = Toolbelt(
        tools,
        policy,
        confirm=_confirm,
        notify=_notify,
        meter=meter,
        hooks=hooks,
        result_budget=_spill_result,
        # Episodic trail: every executed tool call lands in memory/episodic.db
        # (trigger / action / result summary), feeding recall and the organizer
        recorder=EpisodeRecorder(memory.episodic).record_tool,
        # Tool permission modes (one mode + deny/allow lists, hot-read): the
        # agent-actor gate in front of every native tool call
        permissions=ToolPermissions(settings),
    )

    # External MCP: an empty pool is legal; the approve action registers into
    # the root registry via the capability layer (conversation copies from the
    # root next turn), start() only reconnects enabled+approved entries
    mcp = McpClientPool(
        settings=settings,
        toolbelt=toolbelt,
        connect=mcp_connect,
        cwd=workspace,
        auto_refresh=True,
    )

    # Plugins: manifests are scannable (visible in list), loading is restricted
    # to the persisted approval list (union of bundle agent.plugins.approved and
    # per-item agent.plugins.approvals); a listed plugin whose directory was
    # deleted is skipped without breaking startup. MCP entries register only on
    # the approve action, never re-registered at startup.
    # Subscription-sync injection: PluginManager only exists after the EventLoop
    # is constructed, so build the manager first (no injection), run startup
    # loading, then inject; afterwards approvals/revocations push
    # hooks.event_patterns to the loop live (approved = subscribed, revoked =
    # unsubscribed, no restart).
    plugins_root = (
        # src layout: build.py sits at <repo>/agent/src/agent/build.py; the
        # declarative user plugins live at <repo>/plugins/
        Path(plugins_dir) if plugins_dir else (Path(__file__).resolve().parents[3] / "plugins")
    )
    plugins = PluginManager(
        plugins_root, settings=settings, skills=skills, hooks=hooks, mcp=mcp, workspace=workspace
    )
    for plugin_name in plugins.loadable_names():
        if plugins.find(plugin_name) is not None:
            plugins.apply(plugin_name)

    # User hooks hot load/unload: the directory is pinned to this file's
    # workspace/hooks and the reload capability takes no path argument;
    # startup loading already ran via load_dir above, so this is the runtime
    # incremental-ops entry. The subscription-sync callback shares the
    # PluginManager's entry point (injected after the EventLoop is constructed;
    # see set_subscription_sync below).
    user_hooks = UserHookReloader(hooks, workspace / "hooks", plugins=plugins)

    scheduler = Scheduler(max_concurrent=int(settings.get("agent.subagents.max_concurrent")))
    wake_budget = WakeBudget()  # background-completion wakeup gate (per session)
    queue_store = QueueStore(data_dir / "queue.db")
    queue_store.recover()  # jobs stuck 'running' from a crash go back to pending
    checkpoints = CheckpointStore(data_dir / "checkpoints")
    # Startup sweep of orphan .tmp files left by a crash during save's atomic
    # write; anything unsweepable is retried next startup
    purged_tmp = checkpoints.purge_tmp()
    if purged_tmp:
        logging.getLogger("agent.runtime").info(
            "startup sweep purged orphan checkpoint .tmp files: %d", purged_tmp
        )
    # Startup recovery prep: alive checkpoints with resume snapshots become
    # PAUSED awaiting recovery; legacy ones without snapshots stay failed.
    # No-op for an empty directory; instance rebuilding goes through the
    # resume_run capability, not startup
    prepare_resumable_checkpoints(checkpoints)
    # Startup purge of overdue episodes: retention > 0 cleans by retention days;
    # 0 = agent-managed, no automatic cleanup at startup (same semantics as
    # get_memory's lazy purge)
    retention = int(settings.get("agent.memory.retention_days") or 0)
    if retention > 0:
        memory.purge(retention)
    builder = ContextBuilder(
        # Global rules: text frozen in context/rules.py
        rules=list(GLOBAL_RULES),
        memory=memory,
        digests=digests,
        pages=pages,
        skills=skills,  # the skill index stays resident in the system prompt
        scoped_rules=ScopedRules(workspace),  # workspace/AGENTS.md as a directory rule layer
    )

    def _mcp_section() -> str:
        """Server-declared usage instructions (connected, approved servers),
        sorted by sid for stable bytes; omitted when none or disabled."""
        if not settings.get("agent.mcp.instructions"):
            return ""
        entries = mcp.instructions_map()
        if not entries:
            return ""
        blocks = [f"【MCP: {sid}】\n{text.strip()}" for sid, text in entries.items()]
        return "\n\n".join(blocks)

    def _build_system(task, persona_key: str, query: str = "") -> str:
        persona = resolve_persona(persona_key) if persona_key else None
        # Guidelines are hot-read each turn like style: settings changes apply
        # on the next turn
        conduct = str(settings.get("agent.conduct") or "")
        raw = settings.get("agent.guidelines") or {}
        # raw must be a dict; persona keys go through canonical_persona_key
        # (alias lucien -> orchestrator); unknown/user-defined personas have no
        # corresponding key and simply lack the guideline layer
        guideline = (
            str(raw.get(canonical_persona_key(persona_key), "") or "")
            if isinstance(raw, dict)
            else ""
        )
        cards = budget_from_settings(settings)
        # Resident relevance layer (memory read policy): memory hits for the
        # current input, so long-term knowledge surfaces without the model
        # having to call recall_memory. Episodic entries already shown by the
        # recent-cards layer are excluded, not duplicated.
        recall = ""
        if query and cards.recall_facts > 0 and cards.recall_chars > 0 and memory is not None:
            exclude = {
                str(e.get("summary") or "")
                for e in memory.episodic.recent(limit=cards.memory_cards)
            }
            # Profile keys already ride the resident profile layer (Phase A):
            # keep the recall budget for episodic/semantic hits. When the
            # profile layer itself is off, its hits stay eligible here.
            profile_keys = set(memory.profile.all()) if cards.profile_chars > 0 else None
            recall = render_relevant_recall(
                memory,
                query,
                limit=cards.recall_facts,
                max_chars=cards.recall_chars,
                exclude_summaries=exclude,
                exclude_profile_keys=profile_keys,
            )
        # Speaking style: the per-agent override (agent.style.overrides) wins
        # over the global agent.style, mirroring the guidelines lookup above
        raw_styles = settings.get(STYLE_OVERRIDES_KEY) or {}
        style = (
            str(raw_styles.get(canonical_persona_key(persona_key), "") or "")
            if isinstance(raw_styles, dict)
            else ""
        ) or str(settings.get("agent.style") or "")
        return builder.system(
            persona=persona,
            task=task,
            style=style,
            conduct=conduct,
            guideline=guideline,
            memory_cards=cards.memory_cards,
            memory_card_chars=cards.memory_card_chars,
            plan_section=plan_gates.section_for(getattr(task, "session", "")),
            recall_section=recall,
            mcp_section=_mcp_section(),
            skill_max=cards.skill_max,
            skill_chars=cards.skill_chars,
            profile_chars=cards.profile_chars,
            task_chars=cards.task_chars,
            digest_chars=cards.digest_chars,
            page_chars=cards.page_chars,
            mcp_chars=cards.mcp_chars,
        )

    def _budget_model_name() -> str:
        """Model for per-profile window resolution: the client's attr first,
        then the standalone-run setting, then the composer's chat model (what
        an empty-model ServiceLLM actually serves per call). llm-domain keys
        are unregistered in agent-only builds — those reads degrade to empty,
        never raise."""
        probe = str(getattr(llm, "model", "") or "")
        for key in ("agent.llm.model", "llm.default_model"):
            if probe:
                break
            try:
                probe = str(settings.get(key) or "")
            except ServiceError:
                probe = ""
        return probe

    spawner = Spawner(
        llm=chat_llm,
        toolbelt=toolbelt,
        scheduler=scheduler,
        events=events,
        checkpoints=checkpoints,
        build_system=_build_system,
        pages=pages,  # conversational instances preactivate tools per current page
        sync_digest=digests.upsert,  # refresh the DigestStore on steps
        budget_fn=lambda: budget_from_settings(
            settings,
            model_name=_budget_model_name(),
        ),  # hot-read context budget
        planner_llm=planner_llm,  # context editor planning client (may be routed)
    )
    subagent_registry = SubagentRegistry(data_dir / "subagents")
    # Chat session persistence: the main conversation survives restarts; a
    # fresh data dir simply starts empty. Closed with the app.
    session_store = SessionStore(data_dir / "sessions.db")
    distiller = Distiller(llm=distiller_llm, memory=memory, settings=settings)

    # Skill self-organization: repeated tool flows in episodic memory surface
    # as non-blocking skill.proposed notifications (never the ask_user modal);
    # saving goes through the propose_skill tool once the user agrees.
    async def _emit_skill_proposed(**payload: Any) -> None:
        await events.emit(DomainEvent.SKILL_PROPOSED, **payload)

    organizer = SkillOrganizer(memory.episodic, emit=_emit_skill_proposed, settings=settings)
    task_graph = TaskGraph()  # dependency edges between named task dispatches
    blackboard = Blackboard()  # task-scoped shared notes (read/write tools bind it)
    task_board = TaskBoard()  # team publish/claim/confirm board (taskboard capability)
    # One anti-bombing budget shared by every assistant-initiated channel
    # (greetings/follow-ups), so the caps are global.
    outreach_budget = OutreachBudget(settings)
    proactive = ProactiveEngine(
        master=None,
        llm=chat_llm,
        budget=outreach_budget,
        settings=settings,
        scheduler=scheduler,
        queue=queue_store,
    )
    proactive.register_handlers()
    master = Master(
        llm=chat_llm,
        bus=bus,
        spawner=spawner,
        arbiter=Arbiter(arbiter_llm),
        digests=digests,
        settings=settings,
        hooks=hooks,
        memory=memory,
        subagents=subagent_registry,
        policy=policy,  # copied when narrowing a user-defined subagent's network
        session_store=session_store,
        distiller=distiller,
        organizer=organizer,
        wake_budget=wake_budget,
        task_graph=task_graph,
        blackboard=blackboard,
        task_board=task_board,
    )
    # Background completions report through the notifier: quiet notices and
    # budget-gated wakeups share the master's reply/notice channels
    scheduler.set_completion_listener(JobNotifier(master, wake_budget))
    # Session search index: FTS projection over the event log (lazy catch_up
    # keeps it current on reads; the boot fold happens right after assembly)
    session_index = SessionIndex(data_dir / "session_index.db", log)
    # Durable session goals: boot downgrades active goals to paused (an
    # unattended process never resumes them); continuation rounds run through
    # the durable queue with an admission fence
    goal_manager = GoalManager(session_store)
    goal_manager.downgrade_active_to_paused()
    goal_driver = GoalDriver(master, goal_manager, queue_store, settings, scheduler)
    master.goal_driver = goal_driver  # post-turn hook reads it (defaults None)
    # The spawn_subagent and session tools only enter the registry now: the
    # master is ready, so they can bind its public surface directly
    # (conversational instances re-copy from the root registry each turn,
    # visible next message; same injection channel as MCP mounting)
    toolbelt.register(
        {
            **plan_tools(plan_gates, asker),
        }
    )
    jobs_view = JobsView(log)
    registry = build_agent_registry(
        CapabilityDeps(
            settings=settings,
            memory=memory,
            skills=skills,
            spawner=spawner,
            subagents=subagent_registry,
            pages=pages,
            asker=asker,
            toolbelt=toolbelt,
            mcp=mcp,
            meter=meter,  # same instance as Toolbelt / metered_llm (quota queries read the same metering)
            checkpoints=checkpoints,  # resumable checkpoint listing
            plugins=plugins,  # plugin discovery and approval
            user_hooks=user_hooks,  # hot load/unload of user workspace/hooks
            todos=TodoStore(
                workspace / "todo.json"
            ),  # same root as the toolbelt's store; per-session plans derive from it
            sessions=master.sessions,  # same manager the agent session tools use (one engine, two drivers)
            jobs=jobs_view,  # task.* projection (read-only)
            job_cancel=job_cancel,  # host-routed to the source domain's cancel capability
            job_reorder=job_reorder,  # host-routed to the source domain's reorder capability
            blackboard=blackboard,  # task-scoped shared notes (read/write tools below)
            task_board=task_board,  # team task board (taskboard capability + tool)
            task_claim_notify=master.notify_task_claim,  # claim wakes the publisher
            plan_gates=plan_gates,  # human-side review-phase toggle
            dispatch=master.dispatch_task,  # subagent spawn action
            team_handoff=master.queue_member_turn,  # subagent handoff action
            goal_manager=goal_manager,  # durable session goals
            skills_dir=skills_dir,  # skill propose writes here
            session_index=session_index,  # session search action
            log=log,  # session read action pages the shared history
        )
    )
    # Agent-side projection of the agent's own governance/observation
    # capabilities: each tool runs the same registry entry the human REST
    # path mounts, as the agent actor, through the same guard chain and audit
    # sinks (one implementation, two projections). Sessions that the user is
    # looking at are protected by agent-side preconditions; read_events pages
    # the shared event log directly.
    toolbelt.register(
        {
            **team_tools(registry, audit),
            **memory_tools(registry, audit),
            **extension_tools(registry, audit),
            **session_tools(registry, master.sessions, session_index, log, audit),
            **observe_tools(registry, audit),
            **jobs_tools(registry, audit),
            **tools_tools(registry, audit),
        }
    )
    # Trajectory projection: a rebuildable query index over the event log
    # (steps / runs); startup catch-up folds whatever landed while down
    trajectory = TrajectoryStore(data_dir / "trajectory.db", log)
    trajectory.catch_up()
    # Raw LLM round log retention: a debugging surface, not an archive - the
    # bodies are full per-round transcripts and would grow without bound.
    trajectory.purge_raw_older_than_days(RAW_LOG_RETENTION_DAYS)

    def _raw_round_fn(session_id: str):
        """Per-session raw LLM round recorder: the exact request transcript
        plus the response, stored in the trajectory store for the UI's raw
        log view. Bodies are serialized once here, verbatim (retention is
        handled by purge_raw_older_than_days, not a size cap)."""

        async def _record(run_id: str, round_n: int, messages: list, reply: object) -> None:
            # Provider response metadata (finish_reason / request id / service
            # tier / created); empty values dropped so the stored shape stays
            # tight.
            meta = getattr(reply, "meta", None)
            meta_dict = {k: v for k, v in meta.items() if v} if isinstance(meta, dict) else {}
            response = json.dumps(
                {
                    "text": getattr(reply, "text", "") or "",
                    "reasoning": getattr(reply, "reasoning", "") or "",
                    "tool_calls": [
                        {"name": c.name, "arguments": c.arguments}
                        for c in (getattr(reply, "tool_calls", None) or [])
                    ],
                    "degraded": bool(getattr(reply, "degraded", False)),
                    "model": getattr(reply, "model", ""),
                    "meta": meta_dict,
                },
                ensure_ascii=False,
                default=str,
            )
            # The exact provider request body (stream flags, temperature,
            # reasoning fields, tools) as reported by the llm domain's final
            # stream chunk; empty when the client did not report one (FakeLLM,
            # non-streaming paths).
            wire_body = getattr(reply, "request_body", None)
            wire_request = (
                json.dumps(wire_body, ensure_ascii=False, default=str)
                if isinstance(wire_body, dict)
                else ""
            )
            trajectory.record_raw_round(
                run_id=run_id,
                session=session_id,
                round=round_n,
                request=json.dumps(messages, ensure_ascii=False, default=str),
                response=response,
                wire_request=wire_request,
            )

        return _record

    master.sessions.set_raw_fn(_raw_round_fn)
    session_index.catch_up()  # fold whatever landed while the process was down
    trigger_handler = make_trigger_handler(master, subagent_registry, settings=settings)
    handlers, relay, hook_patterns = bind_event_loop(
        master,
        hooks,
        trajectory=trajectory,
        proactive=proactive,
        trigger_handler=trigger_handler,
        trigger_patterns=trigger_patterns(subagent_registry),
    )
    loop = EventLoop(
        bus,
        handlers,
        cursors=cursors,
        relay=relay,
        extra_patterns=hook_patterns,
    )
    # Runtime subscription sync: startup-loaded patterns already arrived via
    # extra_patterns; after injection every approval/revocation has
    # PluginManager push the latest event_patterns to the loop
    plugins.set_subscription_sync(loop.sync_extra_patterns)
    # User hook hot-reload shares the same subscription entry: after reload it
    # pushes the latest event_patterns; a second subscription channel is
    # forbidden
    user_hooks.set_subscription_sync(loop.sync_extra_patterns)

    # Observability and Tracing exporter wiring
    exporter_type = str(settings.get("agent.observability.exporter") or "memory").lower()
    span_exporters: list[Any] = []
    if exporter_type in ("otlp", "all"):
        otlp_endpoint = str(
            settings.get("agent.observability.otlp_endpoint") or "http://localhost:4318/v1/traces"
        )
        span_exporters.append(OtlpHttpSpanExporter(endpoint=otlp_endpoint))
    if exporter_type in ("langfuse", "all"):
        lf_host = str(
            settings.get("agent.observability.langfuse_host") or "https://cloud.langfuse.com"
        )
        lf_pk = str(settings.get("agent.observability.langfuse_public_key") or "")
        lf_sk = str(settings.get("agent.observability.langfuse_secret_key") or "")
        span_exporters.append(
            LangfuseSpanExporter(host=lf_host, public_key=lf_pk, secret_key=lf_sk)
        )
    dispatcher = TraceDispatcher(span_exporters)
    dispatcher.attach()

    return AgentApp(
        bus=bus,
        log=log,
        settings=settings,
        memory=memory,
        master=master,
        loop=loop,
        skills=skills,
        hooks=hooks,
        pages=pages,
        asker=asker,
        spawner=spawner,
        registry=registry,
        mcp=mcp,
        meter=meter,
        plugins=plugins,
        user_hooks=user_hooks,
        session_store=session_store,
        trajectory=trajectory,
        session_index=session_index,
        queue_store=queue_store,
        scheduler=scheduler,
        checkpoints=checkpoints,
        write_journal=write_journal,
        owns_settings=owns_settings,
        owns_log=owns_log,
        dispatcher=dispatcher,
    )


__all__ = ["build_agent"]
