"""Workspace tool group: jailed fs/search/shell/todo tools.

Zero-logic aggregation: the per-tool factories live in their own files; the
`*_tools` helpers here only build one Jail and merge the tool dicts (same
merge shape build_agent and the tests consumed before the split).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent.tools.core.base import AgentTool
from agent.tools.workspace.delete_file import delete_file_tool
from agent.tools.workspace.edit_file import edit_file_tool
from agent.tools.workspace.glob import glob_tool
from agent.tools.workspace.grep import grep_tool
from agent.tools.workspace.jail import Jail
from agent.tools.workspace.list_dir import list_dir_tool
from agent.tools.workspace.read_file import read_file_tool
from agent.tools.workspace.run_shell import run_shell_tool
from agent.tools.workspace.todo_read import todo_read_tool
from agent.tools.workspace.todo_store import TodoStore, read_plan
from agent.tools.workspace.todo_write import todo_write_tool
from agent.tools.workspace.workdir import DEFAULT_CATEGORIES, ensure_workdir
from agent.tools.workspace.write_file import write_file_tool


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
) -> dict[str, AgentTool]:
    """Jailed fs tool group (read/write/edit/list/delete) sharing one Jail."""
    jail = _jail(roots, read_roots, write_roots, read_roots_fn, write_roots_fn)
    tools = (
        read_file_tool(jail),
        write_file_tool(jail),
        edit_file_tool(jail),
        list_dir_tool(jail),
        delete_file_tool(jail),
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
    tool = run_shell_tool(cwd)
    return {tool.name: tool}


def todo_tools(store: TodoStore) -> dict[str, AgentTool]:
    tools = (todo_write_tool(store), todo_read_tool(store))
    return {t.name: t for t in tools}


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
