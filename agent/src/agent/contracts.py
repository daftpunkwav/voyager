"""Cross-package protocol layer: the decoupling point for the agent
domain's inner circle (tools/context/skills/subagent/master).

This module depends only on the standard library and agent.llm (pure types,
pure data, no runtime behavior). Packages in the domain depend only on the
Protocols/aliases here instead of importing each other, keeping the static
dependency graph acyclic - the four package-level cycles previously held
down by TYPE_CHECKING duck typing are formally eliminated by this layer.

Mirrors platform_contracts (platform-level contracts, zero dependencies)
with domain-level contracts; Protocol structural matching means implementors
(skills.loader / subagent.instance / context.loader / tools.core.base) need no
import of this module and no explicit inheritance.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    # Type-checking only: a runtime import would execute the agent.master
    # package __init__, which reads this module (import-order cycle).
    from agent.master.digest import DigestStore

from agent.llm import LLMClient, ToolCall, ToolSpec

# ---- Callback aliases (re-exported in tools/core/base to keep existing import paths) ----

ConfirmFn = Callable[[str], Awaitable[bool]]  # confirmation question -> whether the user agrees
NotifyFn = Callable[[str], Awaitable[None]]  # L1 notice outlet


class SkillRecallSource(Protocol):
    """Sourcing surface for the load_skill / recall_memory tools
    (implemented by context.loader.OnDemandLoader)."""

    def skill_text(self, name: str) -> str: ...

    def recall(self, query: str, limit: int = 8) -> list: ...


class SkillIndexProvider(Protocol):
    """Skill index surface for context assembly (implemented by
    skills.loader.SkillLoader)."""

    def index(self) -> list[dict[str, str]]: ...


class TaskSpec(Protocol):
    """Read-only task-book surface (implemented by subagent.instance.TaskBook,
    a frozen dataclass matched structurally)."""

    @property
    def goal(self) -> str: ...

    @property
    def constraints(self) -> str: ...

    @property
    def done_when(self) -> str: ...


class ToolRunner(Protocol):
    """Tool surface for mode execution (implemented by tools.core.base.Toolbelt /
    trimmed views)."""

    def specs(self) -> list[ToolSpec]: ...

    async def call(self, call: ToolCall) -> str: ...

    async def call_detailed(self, call: ToolCall) -> Any:
        """Same pipeline and text as call(), plus the structured outcome
        (Any here: ToolResult lives in the tool layer, which already depends
        on this module - annotating it would cycle)."""

    def concurrent_safe(self, name: str) -> bool: ...


class Purpose(str, Enum):
    """What an LLM call is for: the routing key for per-purpose models.

    The routing table (agent.llm.routing) maps these to provider/model pairs
    with optional fallbacks; unset purposes fall back to the default
    provider/model resolution.
    """

    CHAT = "chat"
    ARBITER = "arbiter"
    DISTILL = "distill"
    CONTEXT_PLANNER = "context_planner"
    EMBEDDING = "embedding"


class SettingsReader(Protocol):
    """Settings-read protocol: master/spawner depend only on the minimal
    "read a setting" surface (decoupling).

    Consolidated from master/settings_store_protocol.py: the protocol is a
    cross-package shared surface, so it belongs in this layer.
    """

    def get(self, key: str) -> Any: ...


class ToolSource(Protocol):
    """Assembly-time tool supply surface: one named contributor to the
    agent tool roster (a builtin group, the domain bridge, a test fixture).

    Values are AgentTool-shaped entries; Any avoids importing the tool layer
    here (tools.core.base already depends on this module for callbacks).
    Protocol structural matching means implementors need no import of this
    module and no explicit inheritance. Consumed by
    tools.core.registry.ToolRegistry.
    """

    @property
    def source_name(self) -> str: ...

    def tools(self) -> dict[str, Any]: ...


class DispatchMaster(Protocol):
    """The Master surface dispatch_task depends on.

    master.py imports dispatch lazily (dispatch backs two Master methods);
    this protocol keeps that dependency type-only instead of a module cycle.
    sessions is Any for the same reason ToolSource avoids the tool layer:
    SessionManager pulls in the subagent package, which transitively reads
    this module. Protocol structural matching means Master needs no import
    of this module and no explicit inheritance.
    """

    async def reply(self, text: str, *, trace_id: str = "", session: str = "") -> None: ...

    @property
    def digests(self) -> DigestStore: ...

    @property
    def sessions(self) -> Any: ...  # SessionManager surface: active_id()

    #: Chat client, reused for the completion-notice synthesis (see
    #: agent.master.synthesize; metered like every chat path)
    @property
    def llm(self) -> LLMClient: ...

    def finish_task(self, name: str, *, ok: bool) -> None: ...

    def track_background(self, task: Any) -> None: ...
