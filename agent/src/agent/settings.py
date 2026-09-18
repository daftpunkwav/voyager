"""The agent's own settings: everything the user can change the agent can
change too (except secret / user_only, enforced at the framework layer).

Round limits, arbitration mode, memory retention - non-secret and non-user_only, writable by user and
agent alike, always audited. Network / workspace dir / external MCP /
in-app capability whitelists are security boundaries and marked user_only:
only the user can write them (prompt injection cannot), though values are
still echoed back (the settings page shows the current tier).
"""

from platform_settings import SettingDef, SettingType

from agent.context.budgets import (
    DIGEST_CHARS,
    MCP_CHARS,
    PAGE_CHARS,
    PROFILE_CHARS,
    SKILL_CHARS,
    SKILL_MAX,
    TASK_CHARS,
)

# Canonical key strings. Readers (outreach budget, trigger spawns, host
# routing) import these constants instead of repeating the literals, so a
# rename cannot silently detach a reader from its registered default.
OUTREACH_ENABLED_KEY = "agent.outreach.enabled"
OUTREACH_DAILY_MAX_KEY = "agent.outreach.daily_max"
OUTREACH_SESSION_MAX_KEY = "agent.outreach.session_max"
OUTREACH_COOLDOWN_KEY = "agent.outreach.cooldown_minutes"
OUTREACH_QUIET_KEY = "agent.outreach.quiet_hours"
TRIGGERS_COOLDOWN_KEY = "agent.triggers.cooldown_s"
SUBAGENTS_MAX_DEPTH_KEY = "agent.subagents.max_depth"
ROUTING_KEY = "agent.llm.routing"
OVERRIDES_KEY = "agent.llm.overrides"
STYLE_OVERRIDES_KEY = "agent.style.overrides"
WORKSPACE_DIR_KEY = "agent.workspace.dir"

DEFS = [
    SettingDef(
        key=OUTREACH_ENABLED_KEY,
        module="agent",
        type=SettingType.BOOL,
        default=True,
        description="Master switch for proactive outreach (greetings/follow-ups); budgets below still apply",
    ),
    SettingDef(
        key=OUTREACH_DAILY_MAX_KEY,
        module="agent",
        type=SettingType.INT,
        default=3,
        min=0,
        max=100,
        description="Max proactive messages per day (0 = unlimited)",
    ),
    SettingDef(
        key=OUTREACH_SESSION_MAX_KEY,
        module="agent",
        type=SettingType.INT,
        default=1,
        min=0,
        max=50,
        description="Max proactive messages per session per day (0 = unlimited)",
    ),
    SettingDef(
        key=OUTREACH_COOLDOWN_KEY,
        module="agent",
        type=SettingType.INT,
        default=120,
        min=0,
        max=10080,
        description="Minimum minutes between proactive messages (global and per session); 0 = off",
    ),
    SettingDef(
        key=OUTREACH_QUIET_KEY,
        module="agent",
        type=SettingType.STR,
        default="23:00-08:00",
        description='Quiet hours for proactive outreach, "HH:MM-HH:MM" local time (may span midnight; empty = off)',
    ),
    SettingDef(
        key=TRIGGERS_COOLDOWN_KEY,
        module="agent",
        type=SettingType.INT,
        default=300,
        min=0,
        max=86400,
        description="Cooldown between event-triggered subagent spawns of the same definition; 0 = off",
    ),
    SettingDef(
        key="agent.rounds.max",
        module="agent",
        type=SettingType.INT,
        default=20,
        min=1,
        max=200,
        description="ReAct round limit (global default)",
    ),
    SettingDef(
        key="agent.execution.tool_deadline_s",
        module="agent",
        type=SettingType.FLOAT,
        default=90,
        min=0,
        max=3600,
        description="Wall-clock cap for one tool call (seconds); expired calls are cancelled and reported; 0 = off",
    ),
    SettingDef(
        key="agent.execution.round_deadline_s",
        module="agent",
        type=SettingType.FLOAT,
        default=240,
        min=0,
        max=7200,
        description="Wall-clock cap for one completion round (seconds); an expired round winds down gracefully; 0 = off",
    ),
    SettingDef(
        key="agent.rounds.max_tokens",
        module="agent",
        type=SettingType.INT,
        default=0,
        min=0,
        max=10_000_000,
        description="Token budget per turn (input+output); the turn winds down with a partial report when exceeded; 0 = unlimited",
    ),
    SettingDef(
        key="agent.rounds.tool_max",
        module="agent",
        type=SettingType.INT,
        default=40,
        min=1,
        max=500,
        description="Tool-call round limit (global default)",
    ),
    SettingDef(
        key="agent.arbiter.mode",
        module="agent",
        type=SettingType.CHOICE,
        default="queue",
        choices=("auto", "queue", "guide"),
        description="How incoming messages are handled while a task is running",
    ),
    SettingDef(
        key="agent.direct_chat",
        module="agent",
        type=SettingType.BOOL,
        default=False,
        description="Direct-chat mode: simple Q&A answered by the main agent directly (off by default)",
    ),
    SettingDef(
        key="agent.style",
        module="agent",
        type=SettingType.STR,
        default="热心",
        description="Persona style preset (see the team page presets)",
    ),
    # Conduct: rules the user writes in the settings page, injected into the
    # system prompt every turn.
    # user_only: conduct is the user's rules for the agent; prompt injection
    # cannot write it.
    SettingDef(
        key="agent.conduct",
        module="agent",
        type=SettingType.STR,
        default="",
        user_only=True,
        description="General conduct rules for every agent, injected into each conversation's system prompt (user-writable only)",
    ),
    SettingDef(
        key="agent.guidelines",
        module="agent",
        type=SettingType.JSON,
        default={},
        user_only=True,
        description="Per-agent conduct rules {<persona key>: text}, layered on top of the general rules (user-writable only)",
    ),
    SettingDef(
        key=WORKSPACE_DIR_KEY,
        module="agent",
        type=SettingType.STR,
        default="data/workspace",
        user_only=True,
        description="Agent default working directory (user-writable only)",
    ),
    # Additional read roots (file dimension): absolute paths outside the
    # workspace jail readable via fs tools; write/delete stays workspace-only.
    # user_only: security boundary, prompt injection cannot change it.
    SettingDef(
        key="agent.fs.read_roots",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="Additional read-only directories (absolute path list): readable, writes/deletes stay inside the working directory (user-writable only)",
    ),
    # Additional write roots: explicitly user-configured writable directories.
    # Reads are L0; writes/deletes need L2 confirmation ("user dirs are
    # read-only by default; writes require L2").
    # Paths inside the workspace are unaffected (workspace roots win);
    # user_only: security boundary, prompt injection cannot change it.
    SettingDef(
        key="agent.fs.write_roots",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="Additional read-write directories (absolute paths): reads L0, writes/deletes L2, workspace still takes precedence",
    ),
    SettingDef(
        key="agent.network.mode",
        module="agent",
        type=SettingType.CHOICE,
        default="whitelist",
        choices=("off", "whitelist", "all"),
        user_only=True,
        description="Network access mode (user-writable only)",
    ),
    SettingDef(
        key="agent.network.domains",
        module="agent",
        type=SettingType.JSON,
        default=["github.com", "arxiv.org"],
        user_only=True,
        description="Network allowlist domains (user-writable only)",
    ),
    # Plugin bundle approval list: names of plugins approved as a whole;
    # build_agent loads their skills/hooks from it at startup. user_only:
    # loading boundary, prompt injection cannot change it.
    SettingDef(
        key="agent.plugins.approved",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="Plugin names approved as a bundle (user-writable only)",
    ),
    # Plugin per-item approval: {<plugin name>: {skills: list|"*",
    # hooks: list|"*", mcp: list|"*"}} - persistent per-item selection of
    # skills/hooks/MCP. Mutually exclusive with approved (bundle list) on
    # write: per-item approval only enters approvals, bundle approval only
    # enters approved; revoking clears both. Legacy data with only the old key
    # (name in approved) naturally loads as bundle "*" on read (backward
    # compatible). user_only: loading boundary, prompt injection cannot change
    # it (same standing as approved).
    SettingDef(
        key="agent.plugins.approvals",
        module="agent",
        type=SettingType.JSON,
        default={},
        user_only=True,
        description="Per-item plugin approval state: selected skill/hook/MCP recorded per plugin (user-writable only)",
    ),
    SettingDef(
        key="agent.subagents.max_concurrent",
        module="agent",
        type=SettingType.INT,
        default=3,
        min=1,
        max=16,
        description="Subagent concurrency limit",
    ),
    SettingDef(
        key=SUBAGENTS_MAX_DEPTH_KEY,
        module="agent",
        type=SettingType.INT,
        default=3,
        min=1,
        max=8,
        user_only=True,
        description="Max subagent delegation depth (subagent spawning a subagent); user-writable only",
    ),
    SettingDef(
        key="agent.memory.retention_days",
        module="agent",
        type=SettingType.INT,
        default=90,
        min=0,
        max=3650,
        description="Episodic memory retention days; 0 = managed by the agent",
    ),
    SettingDef(
        key="agent.memory.distill_interval",
        module="agent",
        type=SettingType.INT,
        default=10,
        min=0,
        max=100,
        description="Distill durable memories from recent conversation every N user turns; 0 = off",
    ),
    SettingDef(
        key="agent.memory.context_cards",
        module="agent",
        type=SettingType.INT,
        default=5,
        min=0,
        max=50,
        description="Recent episodic memory cards kept resident in the system prompt; 0 = off",
    ),
    SettingDef(
        key="agent.memory.context_card_chars",
        module="agent",
        type=SettingType.INT,
        default=600,
        min=0,
        max=5000,
        description="Character cap of the resident memory-card layer (oldest cards dropped first)",
    ),
    SettingDef(
        key="agent.memory.recall_facts",
        module="agent",
        type=SettingType.INT,
        default=4,
        min=0,
        max=50,
        description="Memory hits relevant to the current input kept resident in the system prompt; 0 = off",
    ),
    SettingDef(
        key="agent.memory.recall_chars",
        module="agent",
        type=SettingType.INT,
        default=600,
        min=0,
        max=5000,
        description="Character cap of the resident relevance-memory layer",
    ),
    SettingDef(
        key="agent.memory.profile_chars",
        module="agent",
        type=SettingType.INT,
        default=PROFILE_CHARS,
        min=0,
        max=5000,
        description="Character cap of the resident user-profile layer; 0 = off",
    ),
    SettingDef(
        key="agent.skills.organize_every",
        module="agent",
        type=SettingType.INT,
        default=30,
        min=0,
        max=1000,
        description="Check episodic memory for repeated tool flows every N tool calls and propose saving them as skills (asks first); 0 = off",
    ),
    # Context engineering budget (token estimates, not bytes). compress_budget:
    # per-turn transcript budget - past it the compactor condenses the middle
    # into a summary. history_max: cross-turn user/assistant entries kept on
    # conversational instances; the oldest turns are dropped in pairs.
    SettingDef(
        key="agent.context.compress_budget",
        module="agent",
        type=SettingType.INT,
        default=6000,
        min=500,
        max=1_000_000,
        description="Per-turn transcript budget (rough token estimate); the compactor summarizes beyond it",
    ),
    SettingDef(
        key="agent.context.history_max",
        module="agent",
        type=SettingType.INT,
        default=60,
        min=2,
        max=1000,
        description="Cross-turn history entries kept per conversation; oldest turns dropped in pairs",
    ),
    SettingDef(
        key="agent.context.tool_result_max",
        module="agent",
        type=SettingType.INT,
        default=8000,
        min=500,
        max=1_000_000,
        description="Per-tool-result character budget; larger results are truncated and spilled to workspace/spill/",
    ),
    SettingDef(
        key="agent.context.tool_result_max_lines",
        module="agent",
        type=SettingType.INT,
        default=2000,
        min=0,
        max=1_000_000,
        description="Per-tool-result line budget (either dimension spills); 0 disables the line dimension",
    ),
    SettingDef(
        key="agent.context.skill_max",
        module="agent",
        type=SettingType.INT,
        default=SKILL_MAX,
        min=0,
        max=500,
        description="Resident skill-index entries shown in the system prompt; 0 = off",
    ),
    SettingDef(
        key="agent.context.skill_chars",
        module="agent",
        type=SettingType.INT,
        default=SKILL_CHARS,
        min=0,
        max=20_000,
        description="Character cap of the resident skill-index layer; 0 = off",
    ),
    SettingDef(
        key="agent.context.mcp_chars",
        module="agent",
        type=SettingType.INT,
        default=MCP_CHARS,
        min=0,
        max=20_000,
        description="Character cap of the MCP instruction layer; 0 = off",
    ),
    SettingDef(
        key="agent.context.digest_chars",
        module="agent",
        type=SettingType.INT,
        default=DIGEST_CHARS,
        min=0,
        max=10_000,
        description="Character cap of the subagent digest layer; 0 = off",
    ),
    SettingDef(
        key="agent.context.task_chars",
        module="agent",
        type=SettingType.INT,
        default=TASK_CHARS,
        min=0,
        max=10_000,
        description="Character cap of the task-brief layer; 0 = off",
    ),
    SettingDef(
        key="agent.context.page_chars",
        module="agent",
        type=SettingType.INT,
        default=PAGE_CHARS,
        min=0,
        max=5000,
        description="Character cap of the page-awareness layer; 0 = off",
    ),
    SettingDef(
        key="agent.pricing.overrides",
        module="agent",
        type=SettingType.JSON,
        default={},
        user_only=True,
        description=(
            "Per-model price overrides (USD per Mtok) for the cost view: "
            '{"<model>": {"input": 1.0, "output": 2.0, "cache_read": 0.1}}; '
            "models without a price stay in the unknown bucket"
        ),
    ),
    SettingDef(
        key="agent.mcp.refresh_seconds",
        module="agent",
        type=SettingType.INT,
        default=300,
        min=0,
        max=86_400,
        description="Interval for hot-refreshing connected MCP servers' tool lists; 0 disables the refresh loop",
    ),
    SettingDef(
        key="agent.mcp.instructions",
        module="agent",
        type=SettingType.BOOL,
        default=True,
        description="Inject connected MCP servers' declared usage instructions into the system prompt",
    ),
    # Model context window (tokens): must match the model's real parameters.
    # Drives the usage status the LLM sees every turn and the auto-compact
    # threshold (usable = window - max_output).
    SettingDef(
        key="agent.context.window_tokens",
        module="agent",
        type=SettingType.INT,
        default=200_000,
        min=1_000,
        max=10_000_000,
        description="Model context window (tokens); enter the model's real value, per-model overrides live in agent.context.model_profiles",
    ),
    SettingDef(
        key="agent.context.max_output_tokens",
        module="agent",
        type=SettingType.INT,
        default=64_000,
        min=256,
        max=1_000_000,
        description="Max output tokens reserved for the reply (the rest of the window is usable transcript)",
    ),
    # Per-model window profiles: {model_name: {window_tokens, max_output_tokens}}.
    # Enter each model's real parameters; unknown/absent models use the global
    # defaults above.
    SettingDef(
        key="agent.context.model_profiles",
        module="agent",
        type=SettingType.JSON,
        default={},
        description='Per-model window limits {"<model>": {"window_tokens": N, "max_output_tokens": N}}; enter real model parameters, unset models fall back to the global defaults',
    ),
    # Auto-compact trigger: percent of the usable window; past it the harness
    # asks the LLM to restructure the transcript (keep/summarize/drop).
    SettingDef(
        key="agent.context.auto_compact_at",
        module="agent",
        type=SettingType.INT,
        default=75,
        min=5,
        max=100,
        description="Auto-compact trigger as percent of the usable context window",
    ),
    # Post-compact target (tokens kept after an LLM compaction); 0 = auto
    # (40% of the usable window). The mechanical fallback keeps its own
    # budget (agent.context.compress_budget).
    SettingDef(
        key="agent.context.compact_target",
        module="agent",
        type=SettingType.INT,
        default=0,
        min=0,
        max=1_000_000,
        description="Tokens kept after an LLM compaction; 0 = auto (40% of the usable window)",
    ),
    # Rolling tool-result prune (microcompact): the newest window of tool
    # output always stays intact; older oversized results are replaced by a
    # sentinel. A prune only fires when at least the recovery floor can be
    # reclaimed, so it never costs a cache break for a handful of tokens.
    SettingDef(
        key="agent.context.prune_protect_tokens",
        module="agent",
        type=SettingType.INT,
        default=4000,
        min=0,
        max=1_000_000,
        description="Rolling prune: newest tool-output tokens (per round) always kept intact",
    ),
    SettingDef(
        key="agent.context.prune_min_tokens",
        module="agent",
        type=SettingType.INT,
        default=2000,
        min=0,
        max=1_000_000,
        description="Rolling prune: minimum recoverable tokens before old tool results are cleared",
    ),
    # External MCP: stdio/URL servers the user added in the settings page.
    # One record: {id,name,kind,command,args,url,approval,approved,enabled};
    # remote schemas / local absolute paths never enter this JSON; connection
    # details live in runtime state.
    # user_only: prompt injection cannot change the server list.
    SettingDef(
        key="agent.mcp.servers",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="External MCP server configs and approval records (user-writable only)",
    ),
    # In-app capability whitelist: user-writable only, hot-read so changes
    # immediately affect bridge tool calls. Names look like
    # `notes__create_note`, `graph__search`; `*` means all; `notes__*` means
    # prefix. An empty allow list rejects every app-dimension tool - the UI
    # must block empty submissions, the backend keeps its semantics unchanged.
    SettingDef(
        key="agent.app.allowed",
        module="agent",
        type=SettingType.JSON,
        default=["*"],
        user_only=True,
        description="In-app capability allowlist (user-writable only)",
    ),
    SettingDef(
        key="agent.app.denied",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="In-app capability denylist (deny wins; user-writable only)",
    ),
    # Shell command-prefix rules: an allow hit skips the L2 confirm only for
    # commands with no write intent (verbs/redirection); deny always rejects.
    # Patterns are token prefixes: `git status` matches exactly; a trailing
    # `*` (`git diff *`) matches the head plus any remaining arguments.
    # user_only: widening the confirm envelope is the user's prerogative.
    SettingDef(
        key="agent.shell.allowed",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="Shell command prefix allowlist (skips L2 for read-only commands; user-writable only)",
    ),
    SettingDef(
        key="agent.shell.denied",
        module="agent",
        type=SettingType.JSON,
        default=[],
        user_only=True,
        description="Shell command prefix denylist (deny wins over allow; user-writable only)",
    ),
    # Daily token quota (resource dimension): hot-read before each complete of
    # the main-conversation LLM; once the current UTC day's input+output total
    # reaches the cap, real calls are refused; 0 = unlimited.
    # user_only: resource security boundary, prompt injection cannot write it
    # (prevents self-raised quotas).
    SettingDef(
        key="agent.resource.daily_tokens",
        module="agent",
        type=SettingType.INT,
        default=0,
        min=0,
        max=10_000_000,
        user_only=True,
        description="Daily LLM token quota (input+output combined); 0 = unlimited (user-writable only)",
    ),
    # Standalone-run LLM endpoint (REPL / python -m agent.main): any
    # OpenAI-compatible /chat/completions service. Aggregate runs ignore these
    # keys - the host injects its own adapter. base_url/key are security
    # boundaries: user_only, and the key is a secret (write-only, never echoed).
    SettingDef(
        key=ROUTING_KEY,
        module="agent",
        type=SettingType.JSON,
        default={},
        description=(
            'Per-purpose model routing: {"<purpose>": {"provider": "<id>", "model": "<name>", '
            '"fallbacks": [{"provider": "", "model": ""}]}}; purposes: chat / arbiter / distill / '
            "context_planner / embedding. Empty entries fall back to the default provider/model."
        ),
    ),
    SettingDef(
        key=OVERRIDES_KEY,
        module="agent",
        type=SettingType.JSON,
        default={},
        description=(
            'Per-persona model overrides: {"<persona key>": {"provider": "<id>", "model": "<name>", '
            '"fallbacks": [{"provider": "", "model": ""}]}}. Consulted per turn for the '
            "conversation's persona; empty provider/model fields fall back to the default resolution."
        ),
    ),
    SettingDef(
        key=STYLE_OVERRIDES_KEY,
        module="agent",
        type=SettingType.JSON,
        default={},
        user_only=True,
        description="Per-agent speaking styles {<persona key>: text}, layered over agent.style for that persona (user-writable only)",
    ),
    SettingDef(
        key="agent.llm.base_url",
        module="agent",
        type=SettingType.STR,
        default="",
        user_only=True,
        description="Standalone-run LLM endpoint (OpenAI-compatible chat-completions base URL); empty = FakeLLM (user-writable only)",
    ),
    SettingDef(
        key="agent.llm.api_key",
        module="agent",
        type=SettingType.STR,
        default="",
        secret=True,
        description="Standalone-run LLM API key (secret, never echoed back)",
    ),
    SettingDef(
        key="agent.llm.model",
        module="agent",
        type=SettingType.STR,
        default="",
        description="Standalone-run LLM model name",
    ),
    SettingDef(
        key="agent.llm.timeout_s",
        module="agent",
        type=SettingType.INT,
        default=120,
        min=5,
        max=600,
        description="Standalone-run LLM request timeout (seconds)",
    ),
    # Observability and Tracing settings (OpenTelemetry / Langfuse)
    SettingDef(
        key="agent.observability.exporter",
        module="agent",
        type=SettingType.CHOICE,
        default="memory",
        choices=("memory", "otlp", "langfuse", "all"),
        description="Tracing span exporter backend: memory (local buffer only) | otlp (OpenTelemetry) | langfuse | all",
    ),
    SettingDef(
        key="agent.observability.otlp_endpoint",
        module="agent",
        type=SettingType.STR,
        default="http://localhost:4318/v1/traces",
        user_only=True,
        description="OpenTelemetry OTLP/HTTP traces ingest endpoint",
    ),
    SettingDef(
        key="agent.observability.langfuse_host",
        module="agent",
        type=SettingType.STR,
        default="https://cloud.langfuse.com",
        user_only=True,
        description="Langfuse service host URL",
    ),
    SettingDef(
        key="agent.observability.langfuse_public_key",
        module="agent",
        type=SettingType.STR,
        default="",
        user_only=True,
        description="Langfuse public API key (pk-lf-...)",
    ),
    SettingDef(
        key="agent.observability.langfuse_secret_key",
        module="agent",
        type=SettingType.STR,
        default="",
        secret=True,
        description="Langfuse secret API key (sk-lf-...; secret, never echoed)",
    ),
    # Evaluation and Self-Improvement settings
    SettingDef(
        key="agent.evaluation.enabled",
        module="agent",
        type=SettingType.BOOL,
        default=True,
        description="Enable automatic turn evaluation and self-improvement feedback logging",
    ),
    SettingDef(
        key="agent.evaluation.mode",
        module="agent",
        type=SettingType.CHOICE,
        default="heuristic",
        choices=("heuristic", "judge"),
        description="Evaluation strategy: heuristic (fast, zero token cost) | judge (LLM evaluation)",
    ),
    SettingDef(
        key="agent.evaluation.min_score_threshold",
        module="agent",
        type=SettingType.FLOAT,
        default=0.6,
        min=0.0,
        max=1.0,
        description="Minimum score threshold (0.0 - 1.0) for considering a turn passed",
    ),
]
