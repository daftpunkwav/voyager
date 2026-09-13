"""undo_writes tool: roll back recent write_file/edit_file/delete_file
operations via the write journal (newest first).

Safety: an entry is only restored when the file is exactly in the state the
journal saw after the write; a file changed since then is reported and
skipped. Undo of undo is not supported (undone entries are marked), the
tool restores, it never re-applies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.tools.core.base import AgentTool

if TYPE_CHECKING:
    from agent.tools.workspace.write_journal import WriteJournal


def undo_writes_tool(journal: WriteJournal) -> AgentTool:
    def undo_writes(count: int = 1, recent: int = 0) -> Any:
        if recent > 0:
            entries = journal.recent(min(recent, 50))
            return {
                "recent": [
                    {
                        "seq": e.seq,
                        "op": e.op,
                        "path": e.path,
                        "undone": e.undone,
                    }
                    for e in entries
                ]
            }
        if count < 1:
            return "[参数错误] count 至少为 1"
        return journal.undo(min(count, 50))

    return AgentTool(
        name="undo_writes",
        description=(
            "回滚最近的写操作(write/edit/delete,新到旧);文件在写入后又被改动过则跳过。"
            "先设 recent=N 查看最近 N 条写记录"
        ),
        handler=undo_writes,
        dimension="fs",
        write=True,
        # L2 confirm like delete: an undo overwrites current file state, the
        # human stays in the loop even though the restore itself is guarded
        irreversible=True,
        schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "recent": {"type": "integer"},
            },
        },
    )


__all__ = ["undo_writes_tool"]
