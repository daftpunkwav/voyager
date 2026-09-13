"""delete_file tool: jailed single-file deletion (irreversible, L2 confirm).

With a write journal the deleted content is backed up, so undo_writes can
bring the file back while the path stays unoccupied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail
from agent.tools.workspace.write_journal import safe_capture, safe_finalize

if TYPE_CHECKING:
    from agent.tools.workspace.write_journal import WriteJournal


def delete_file_tool(jail: Jail, journal: WriteJournal | None = None) -> AgentTool:
    def delete_file(path: str) -> dict[str, str] | str:
        target = jail.resolve(path, allow_write_roots=True)
        try:
            entry = safe_capture(journal, target, intent="delete")
            target.unlink()
        except FileNotFoundError:
            return f"[失败] 文件不存在: {jail.display(target)}"
        except (IsADirectoryError, PermissionError):
            # Windows reports directories as PermissionError; re-check to
            # keep the message truthful, genuine permission faults propagate.
            if target.is_dir():
                return f"[参数错误] path 是目录: {jail.display(target)}"
            raise
        safe_finalize(journal, entry, target)
        return {"deleted": str(target)}

    return AgentTool(
        name="delete_file",
        description="删除工作目录内文件(不可逆,需用户确认;删除内容可被 undo_writes 找回)",
        handler=delete_file,
        dimension="fs",
        write=True,
        irreversible=True,
        schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    )


__all__ = ["delete_file_tool"]
