"""Workspace tool group: jailed fs/search/shell/todo tools.

Zero-logic aggregation: the per-tool factories live in their own files; the
`*_tools` helpers here only build one Jail and merge the tool dicts (same
merge shape build_agent and the tests consumed before the split).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from agent.tools.core.base import AgentTool
from agent.tools.workspace.bash import bash_tool
from agent.tools.workspace.edit import edit_tool
from agent.tools.workspace.glob import glob_tool
from agent.tools.workspace.grep import grep_tool
from agent.tools.workspace.jail import Jail
from agent.tools.workspace.read import read_tool
from agent.tools.workspace.todo_store import TodoStore, read_plan
from agent.tools.workspace.todowrite import todowrite_tool
from agent.tools.workspace.workdir import DEFAULT_CATEGORIES, ensure_workdir
from agent.tools.workspace.write import write_tool

if TYPE_CHECKING:
    from agent.tools.workspace.write_journal import WriteJournal


def _jail(
    roots: list[str | Path],
    read_roots: list[str | Path] | None,
    write_roots: list[str | Path] | None,
    read_roots_fn: Callable[[], list[str | Path]] | None,
    write_roots_fn: Callable[[], list[str | Path]] | None,
) -> Jail:
    return Jail(
        roots,
        read_roots=read_roots,
        write_roots=write_roots,
        read_roots_fn=read_roots_fn,
        write_roots_fn=write_roots_fn,
    )


def fs_tools(
    roots: list[str | Path],
    read_roots: list[str | Path] | None = None,
    write_roots: list[str | Path] | None = None,
    *,
    read_roots_fn: Callable[[], list[str | Path]] | None = None,
    write_roots_fn: Callable[[], list[str | Path]] | None = None,
    journal: WriteJournal | None = None,
) -> dict[str, AgentTool]:
    """Jailed fs tool group (read/write/edit) sharing one Jail. The write
    journal, when present, keeps content-addressed backups behind the write
    tools (checkpoint/audit support); there is no undo tool on the surface."""
    jail = _jail(roots, read_roots, write_roots, read_roots_fn, write_roots_fn)
    tools = (
        read_tool(jail),
        write_tool(jail, journal),
        edit_tool(jail, journal),
    )
    return {t.name: t for t in tools}


def search_tools(
    roots: list[str | Path],
    read_roots: list[str | Path] | None = None,
    write_roots: list[str | Path] | None = None,
    *,
    read_roots_fn: Callable[[], list[str | Path]] | None = None,
    write_roots_fn: Callable[[], list[str | Path]] | None = None,
) -> dict[str, AgentTool]:
    """Jailed search tool group (grep/glob) sharing one Jail."""
    jail = _jail(roots, read_roots, write_roots, read_roots_fn, write_roots_fn)
    tools = (grep_tool(jail), glob_tool(jail))
    return {t.name: t for t in tools}


def shell_tools(cwd: str | Path) -> dict[str, AgentTool]:
    shell = bash_tool(cwd)
    return {shell.name: shell}


def todo_tools(store: TodoStore) -> dict[str, AgentTool]:
    todo = todowrite_tool(store)
    return {todo.name: todo}


__all__ = [
    "DEFAULT_CATEGORIES",
    "Jail",
    "TodoStore",
    "ensure_workdir",
    "fs_tools",
    "read_plan",
    "search_tools",
    "shell_tools",
    "todo_tools",
]
