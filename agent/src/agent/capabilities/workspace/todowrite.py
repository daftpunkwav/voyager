"""todowrite capability: the human side of the plan surface, same name and
same operation as the agent's todowrite tool — both bind plan_action() in
todo_store (one implementation, two drivers, no human/agent asymmetry).
One action parameter covers the lifecycle: query (the plan panel's poll),
set / update / delete (human curation of a plan). Plans are per chat
session: callers pass the open session's id; omitted/empty addresses the
shared global plan.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.tools.workspace.todo_store import plan_action


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="todowrite",
        description=(
            "Manage the task plan (todo list): action set/query/update/delete over"
            " one session's plan with progress"
        ),
    )
    def todowrite(
        action: str = "query",
        items: list[dict[str, Any]] | None = None,
        index: int | None = None,
        content: str | None = None,
        status: str | None = None,
        session: str = "",
    ) -> dict:
        return plan_action(
            deps.todos.for_session(session),
            action=action,
            items=items,
            index=index,
            content=content,
            status=status,
        )
