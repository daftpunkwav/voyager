"""delete_file tool: jailed single-file deletion (irreversible, L2 confirm)."""

from __future__ import annotations

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail


def delete_file_tool(jail: Jail) -> AgentTool:
    def delete_file(path: str) -> dict[str, str] | str:
        target = jail.resolve(path, allow_write_roots=True)
        try:
            target.unlink()
        except FileNotFoundError:
            return f"[失败] 文件不存在: {jail.display(target)}"
        except (IsADirectoryError, PermissionError):
            # Windows reports directories as PermissionError; re-check to
            # keep the message truthful, genuine permission faults propagate.
            if target.is_dir():
                return f"[参数错误] path 是目录: {jail.display(target)}"
            raise
        return {"deleted": str(target)}

    return AgentTool(
        name="delete_file",
        description="删除工作目录内文件(不可逆,需用户确认)",
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
