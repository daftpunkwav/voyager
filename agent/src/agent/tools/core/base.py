"""AgentTool and Toolbelt: types and roster for agent tools.

Key design: when dispatching a subagent, trimmed() performs capability-surface
trimming — "cannot write files" is not a verbal constraint; the write tool is
genuinely absent. Every call goes through a policy check; L1
prompts, L2 asks the user via the confirm callback.

Call implementation lives in agent.tools.core.invoke; Toolbelt.call remains a thin
wrapper and the public API is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.runtime.recovery import CircuitBreaker

from agent.contracts import ConfirmFn, NotifyFn  # moved to contracts; re-exported for compatibility
from agent.hooks.triggers import HookRegistry
from agent.llm import ToolCall, ToolSpec
from agent.policy import PolicyEngine
from agent.runtime.meter import Meter
from agent.tools.core.model import (
    AgentTool,
    RecorderFn,
    ResultBudgetFn,
    ScopedConfirmFn,
    ToolbeltView,
)
from agent.tools.core.outcome import ToolResult


class Toolbelt:
    def __init__(
        self,
        tools: dict[str, AgentTool],
        policy: PolicyEngine,
        *,
        confirm: ConfirmFn | None = None,
        notify: NotifyFn | None = None,
        meter: Meter | None = None,
        active: set[str] | None = None,
        hooks: HookRegistry | None = None,
        retries: int = 2,  # retries after handler failure; always 0 for write tools
        retry_backoff: float = 0.1,  # backoff start (seconds); tests inject 0 to skip sleeping
        breakers: dict[str, CircuitBreaker] | None = None,  # per-tool; shared by trimmed views
        result_budget: ResultBudgetFn | None = None,  # oversized-result spill; shared by views
        recorder: RecorderFn | None = None,  # episodic recorder; shared by views
        approvals: Any = None,  # approval memory; shared by views
        confirm_scoped: ScopedConfirmFn | None = None,  # three-way L2 confirm; shared by views
    ) -> None:
        self._tools = dict(tools)
        self._policy = policy
        self._confirm = confirm
        self._notify = notify
        self._meter = meter
        self._active = active  # graded loading: when set, specs() returns only the activation set
        self._hooks = hooks  # tool lifecycle hooks: pre/post_tool
        self._retries = retries
        self._retry_backoff = retry_backoff
        self._breakers = breakers if breakers is not None else {}
        self._result_budget = result_budget
        self._recorder = recorder
        self._approvals = approvals
        self._confirm_scoped = confirm_scoped

    def names(self) -> list[str]:
        return sorted(self._tools)

    def concurrent_safe(self, name: str) -> bool:
        """Whether one tool may run in parallel with other same-round calls
        (read-only by nature); unknown names default to False (conservative)."""
        tool = self._tools.get(name)
        return bool(tool and tool.concurrent_safe)

    def register(self, tools: dict[str, AgentTool]) -> None:
        """Merge tools into the root roster in place (external MCP): conversational
        instances re-copy the roster from the root each turn, so new tools are
        visible from the next turn; existing same-name tools are overwritten
        (unregister first when re-mounting after approval)."""
        self._tools.update(tools)

    def unregister(self, names: Iterable[str]) -> None:
        """Remove tools from the root roster in place (removing an MCP server /
        clearing leftovers before re-mounting); missing names are ignored."""
        for n in names:
            self._tools.pop(n, None)

    def specs(self) -> list[ToolSpec]:
        names = self.names()
        if self._active is not None:
            # Names missing from the activation set are naturally absent; call()
            # is not restricted (invoking a non-activated name still works — the
            # timeout problem comes only from schema volume)
            names = [n for n in names if n in self._active]
        return [
            ToolSpec(name=t.name, description=t.description, schema=t.schema)
            for t in (self._tools[n] for n in names)
        ]

    def trimmed(self, allow: Iterable[str] | None) -> Toolbelt:
        """Capability-surface trimming: allow=None returns self unchanged;
        otherwise only whitelisted tools are kept.

        Whitelist entries support **prefix grants**: a trailing `*` (e.g.
        `notes__*`) expands against the **current roster** — bridge tools are
        not yet registered when persona modules are imported, so hard-coding
        expansions in persona files is forbidden; newly mounted domain tools
        automatically enter the trimmed surface.
        """
        if allow is None:
            return self
        entries = list(allow)
        prefixes = tuple(a[:-1] for a in entries if a.endswith("*") and len(a) > 1)
        exact = {a for a in entries if not a.endswith("*")}
        keep = {n for n in self._tools if n in exact or any(n.startswith(p) for p in prefixes)}
        return Toolbelt(
            {n: t for n, t in self._tools.items() if n in keep},
            self._policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            hooks=self._hooks,
            retries=self._retries,
            retry_backoff=self._retry_backoff,
            breakers=self._breakers,
            result_budget=self._result_budget,
            recorder=self._recorder,
            approvals=self._approvals,
            confirm_scoped=self._confirm_scoped,
        )

    def trimmed_read_only(self) -> Toolbelt:
        """Default-deny read surface: drop every write/irreversible tool from
        the roster, whatever the trim allowlist produced.

        Capability removal by construction (the tool is genuinely absent, not
        prompt-constrained); computed from tool metadata, so newly mounted
        write tools are excluded automatically. Read tools (including network
        reads) stay.
        """
        return Toolbelt(
            {n: t for n, t in self._tools.items() if not (t.write or t.irreversible)},
            self._policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            hooks=self._hooks,
            retries=self._retries,
            retry_backoff=self._retry_backoff,
            breakers=self._breakers,
            result_budget=self._result_budget,
            recorder=self._recorder,
            approvals=self._approvals,
            confirm_scoped=self._confirm_scoped,
        )

    def with_active(self, active: set[str], extra: dict[str, AgentTool] | None = None) -> Toolbelt:
        """Graded-loading view: shares the policy engine / confirm channel while
        specs() returns only the activation set.

        active is a **shared reference**: the activate_tools handler mutates it
        in place and the next specs() call sees the new surface; call() is not
        restricted (everything stays callable). `extra` is used to merge in
        built-ins bound to that activation set (activate_tools) without
        touching the global Toolbelt (shared across instances).
        """
        tools = dict(self._tools)
        if extra:
            tools.update(extra)
        return Toolbelt(
            tools,
            self._policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            active=active,
            hooks=self._hooks,
            retries=self._retries,
            retry_backoff=self._retry_backoff,
            breakers=self._breakers,
            result_budget=self._result_budget,
            recorder=self._recorder,
            approvals=self._approvals,
            confirm_scoped=self._confirm_scoped,
        )

    def with_policy(self, policy: PolicyEngine) -> Toolbelt:
        """Swap in another policy engine (dispatch-time narrowing): same tool
        table, new decision engine; usually applied after trimmed(), and never
        reached into via private fields from outside."""
        return Toolbelt(
            self._tools,
            policy,
            confirm=self._confirm,
            notify=self._notify,
            meter=self._meter,
            active=self._active,
            hooks=self._hooks,
            retries=self._retries,
            retry_backoff=self._retry_backoff,
            breakers=self._breakers,
            result_budget=self._result_budget,
            recorder=self._recorder,
            approvals=self._approvals,
            confirm_scoped=self._confirm_scoped,
        )

    @property
    def approvals_store(self) -> Any:
        return self._approvals

    @property
    def scoped_confirm(self) -> ScopedConfirmFn | None:
        return self._confirm_scoped

    def invocation_view(self) -> ToolbeltView:
        """Constrained invocation view of the current roster: the only sanctioned
        way for invoke.py to access a Toolbelt."""
        return ToolbeltView(
            tools=dict(self._tools),
            policy=self._policy,
            confirm=self._confirm,
            notify=self._notify,
            hooks=self._hooks,
            meter=self._meter,
            retries=self._retries,
            retry_backoff=self._retry_backoff,
            breakers=self._breakers,
            result_budget=self._result_budget,
            recorder=self._recorder,
            approvals=self._approvals,
            confirm_scoped=self._confirm_scoped,
        )

    async def call(self, call: ToolCall) -> str:
        """Execute one tool call; the implementation lives in invoke.py and this
        stays a thin wrapper to preserve the public API."""
        from agent.tools.core.invoke import invoke_tool

        return await invoke_tool(self.invocation_view(), call)

    async def call_detailed(self, call: ToolCall) -> ToolResult:
        """Execute one tool call and return the full outcome (same pipeline
        and same LLM-facing text as call())."""
        from agent.tools.core.invoke import invoke_detailed

        return await invoke_detailed(self.invocation_view(), call)
