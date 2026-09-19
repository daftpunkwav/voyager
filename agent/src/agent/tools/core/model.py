"""Data model of the tool-call pipeline: AgentTool (the tool record) and
ToolbeltView (the constrained invocation surface invoke.py receives), plus
the callback type aliases both sides share.

Leaf module: types only, no behavior — base (the Toolbelt roster) and invoke
(the execution pipeline) both depend on it, so the dependency between them
stays one-way.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.policy.permissions import ToolPermissions
    from agent.runtime.recovery import CircuitBreaker

from agent.contracts import ConfirmFn, NotifyFn
from agent.hooks.triggers import HookRegistry
from agent.policy import PolicyEngine
from agent.runtime.meter import Meter

#: Post-processing hook for stringified tool results: (result, tool_name) ->
#: possibly replaced result (oversized-output spill). Absent = passthrough.
ResultBudgetFn = Callable[[str, str], str]

#: Post-call episode recorder: (tool_name, arguments, ok, result_text) ->
#: None (episodic memory). Absent = nothing recorded.
RecorderFn = Callable[[str, dict[str, Any], bool, str], None]

#: Scope-aware L2 confirmation: (prompt, tool, target) -> "allow" | "session"
#: | "always" | "deny". Absent = the plain boolean confirm path.
ScopedConfirmFn = Callable[[str, str, str], Awaitable[str]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: Callable[..., Any]
    schema: dict[str, Any] = field(default_factory=dict)
    dimension: str = "none"  # fs | network | shell | app | skill | plan | resource | none
    write: bool = False
    irreversible: bool = False
    timeout_s: float | None = None  # per-call cap; None = rely on the handler's own limits
    concurrent_safe: bool = False  # read-only by nature: same-round calls may run in parallel


@dataclass(frozen=True)
class ToolbeltView:
    """Constrained invocation view for invoke.py: the minimal execution surface
    Toolbelt exposes.

    invoke no longer digs into Toolbelt private fields; the view is built fresh
    on every Toolbelt.call — `tools` is a snapshot of the current roster
    (register/unregister visible immediately), `breakers` is a shared dict
    (lazily created breakers write back to the original dict, so rebuilding or
    narrowing the view does not reset them).
    """

    tools: dict[str, AgentTool]
    policy: PolicyEngine
    confirm: ConfirmFn | None
    notify: NotifyFn | None
    hooks: HookRegistry | None
    meter: Meter | None
    retries: int
    retry_backoff: float
    breakers: dict[str, CircuitBreaker]
    result_budget: ResultBudgetFn | None = None
    recorder: RecorderFn | None = None
    approvals: Any = None  # policy.approvals.ApprovalStore (remembered L2 grants)
    confirm_scoped: ScopedConfirmFn | None = None
    permissions: ToolPermissions | None = None  # tool permission modes (agent actor)

    def tool(self, name: str) -> AgentTool | None:
        return self.tools.get(name)


__all__ = [
    "AgentTool",
    "RecorderFn",
    "ResultBudgetFn",
    "ScopedConfirmFn",
    "ToolbeltView",
]
