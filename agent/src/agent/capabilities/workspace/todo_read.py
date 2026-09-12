"""todo_read capability: expose the agent's current task plan to the UI.

Same name, same operation as the agent's todo_read tool — both bind to
read_plan() in agent.tools.workspace.todo_store (one implementation, two
drivers). Read-only by design: the plan's shape stays the agent's
responsibility.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.tools.workspace.todo_store import read_plan


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="todo_read",
        description="Current task plan (todo list) with progress; same operation as the agent's todo_read tool",
    )
    def todo_read() -> dict:
        return read_plan(deps.todos)
