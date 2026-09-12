"""edit_file tool: atomic in-place string replacement inside the jail.

Text files only; binary heads are refused. The write is temp-file +
os.replace so an interrupted edit never leaves a half-written target.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail


def edit_file_tool(jail: Jail) -> AgentTool:
    def edit_file(path: str, old_text: str, new_text: str, count: int = 1) -> Any:
        """Atomic string replacement: replaces up to `count` occurrences and
        fails when there are more (default 1 = the match must be unique, so a
        short old_text never rewrites the wrong place). Text files only."""
        target = jail.resolve(path, allow_write_roots=True)
        if target.is_dir():
            return f"[参数错误] path 是目录: {jail.display(target)}"
        if not (old_text or ""):
            return "[参数错误] old_text 不能为空"
        if count < 1:
            return "[参数错误] count 至少为 1"
        try:
            raw = target.read_bytes()
        except FileNotFoundError:
            return f"[失败] 文件不存在: {jail.display(target)}"
        if b"\x00" in raw[:8192]:
            return "[失败] 二进制文件不支持 edit,请用 write_file 整体重写"
        text = raw.decode("utf-8", errors="replace")
        found = text.count(old_text)
        if found == 0:
            return "[失败] 未找到匹配: 请用 read_file/grep 先看原文"
        if found > count:
            return (
                f"[失败] 匹配 {found} 处,超过 count={count}: 请加长 old_text 使其唯一,或增大 count"
            )
        updated = text.replace(old_text, new_text, found)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write (same discipline as TodoStore): temp file + os.replace.
        # newline="": no CRLF translation on write, so a Windows \r\n file
        # round-trips byte-identical outside the replaced span (write_text
        # would double every \r to \r\r\n). Matching stays literal: a
        # multi-line old_text with \n does not match \r\n files.
        tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(updated)
        os.replace(tmp, target)
        return {"edited": jail.display(target), "replacements": found}

    return AgentTool(
        name="edit_file",
        description="在工作目录内原子替换文件片段(old_text 须唯一,多处匹配会失败;大改用 write_file)",
        handler=edit_file,
        dimension="fs",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    )


__all__ = ["edit_file_tool"]
