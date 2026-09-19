"""read tool: jailed text read with a 1-based line window.

Reads see the workspace roots plus the additional read-only and read-write
roots (the jail is the inner layer; the Toolbelt policy check is the outer).
"""

from __future__ import annotations

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail

#: Full-read byte cap for read: truncation happens after reading, and
#: without a cap a multi-hundred-MB generated log/dump would be loaded into
#: memory in full first
_MAX_READ_BYTES = 4_000_000


def read_tool(jail: Jail) -> AgentTool:
    def read(path: str, offset: int = 1, limit: int = 0, max_chars: int = 8000) -> str:
        """Read a text file; offset/limit select a 1-based line window
        (limit 0 = to the end). The default call keeps the legacy
        whole-read output byte-identical."""
        target = jail.resolve(path, allow_read_roots=True, allow_write_roots=True)
        if target.is_dir():
            return f"[参数错误] path 是目录,请用 list_dir: {jail.display(target)}"
        if offset < 1:
            return "[参数错误] offset 从 1 开始"
        if limit < 0:
            return "[参数错误] limit 不能为负数(0 表示读到末尾)"
        if max_chars < 0:
            return "[参数错误] max_chars 不能为负数"
        try:
            size = target.stat().st_size
        except FileNotFoundError:
            return f"[失败] 文件不存在: {jail.display(target)}"
        if size > _MAX_READ_BYTES:
            raise ValueError(
                f"文件过大({size} 字节 > 上限 {_MAX_READ_BYTES}),read 拒绝整读;"
                "请用 offset/limit 分段读取"
            )
        text = target.read_text(encoding="utf-8", errors="replace")
        if offset == 1 and limit == 0:
            return text if len(text) <= max_chars else text[:max_chars] + "\n…[截断]"
        lines = text.splitlines()
        total = len(lines)
        if offset > total:
            return f"[{jail.display(target)}: 共 {total} 行](空: offset 超出总行数)"
        window = lines[offset - 1 :] if limit == 0 else lines[offset - 1 : offset - 1 + limit]
        shown_to = min(offset - 1 + len(window), total)
        body = "\n".join(window)
        head = f"[{jail.display(target)}: 第 {offset}-{shown_to} 行 / 共 {total} 行]"
        if len(body) > max_chars:
            return head + "\n" + body[:max_chars] + "\n…[截断]"
        return head + "\n" + body

    return AgentTool(
        name="read",
        description="读工作目录内文件文本(offset/limit 取 1 起始的行窗,limit 0 到末尾;默认截断 8000 字)",
        handler=read,
        dimension="fs",
        concurrent_safe=True,  # read-only: safe to batch in parallel
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "max_chars": {"type": "integer"},
            },
            "required": ["path"],
        },
    )


__all__ = ["read_tool"]
