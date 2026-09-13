"""write_file tool: jailed whole-file write (parent directories created).

Writes are confined to the workspace roots and the additional read-write
roots; the L2 tier for user directories is judged by the policy layer.
An optional write journal snapshots the previous content so undo_writes
can roll the write back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail
from agent.tools.workspace.write_journal import safe_capture, safe_finalize

if TYPE_CHECKING:
    from agent.tools.workspace.write_journal import WriteJournal


def write_file_tool(jail: Jail, journal: WriteJournal | None = None) -> AgentTool:
    def write_file(path: str, content: str) -> dict:
        target = jail.resolve(path, allow_write_roots=True)
        entry = safe_capture(journal, target, intent="write")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        safe_finalize(journal, entry, target)
        return {"written": str(target), "chars": len(content)}

    return AgentTool(
        name="write_file",
        description="在工作目录内写文件(自动建父目录;写入前的旧内容可被 undo_writes 回滚)",
        handler=write_file,
        dimension="fs",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    )


__all__ = ["write_file_tool"]
