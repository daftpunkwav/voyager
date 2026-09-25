"""board capability: the task-scoped shared blackboard — action read
(task,limit) / write (text,task,author; <=500 chars). Sibling subagents
coordinate through it; cards are capped.

Defaults (task = the calling instance's goal, author = the instance name)
resolve through the executing instance's context on the agent path; a human
REST call passes them explicitly (or gets the global task scope).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.current import current_instance

if TYPE_CHECKING:
    from agent.orchestrator.blackboard import Blackboard


def board_action(
    blackboard: Blackboard,
    *,
    action: str,
    task: str = "",
    limit: int = 20,
    text: str = "",
    author: str = "",
) -> dict | list:
    inst = current_instance.get()
    default_task = inst.task.goal[:80] if inst is not None else ""
    default_author = inst.name if inst is not None else "chat"
    if action == "read":
        return {"items": blackboard.read(task=task or default_task, limit=limit)}
    if action == "write":
        body = str(text or "").strip()
        if not body:
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "text must not be empty")
        return blackboard.write(
            task=task or default_task, text=body, author=author or default_author
        )
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: read/write",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="board",
        description=(
            "Task-shared blackboard: action read (task,limit — notes left by"
            " sibling subagents) / write (text <=500 chars, task, author)"
        ),
    )
    def board(
        action: str, task: str = "", limit: int = 20, text: str = "", author: str = ""
    ) -> dict | list:
        return board_action(
            deps.blackboard, action=action, task=task, limit=limit, text=text, author=author
        )
