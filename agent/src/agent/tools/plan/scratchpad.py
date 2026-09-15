"""scratchpad tool: in-harness working scratchpad for intermediate thinking and step tracking.

Provides persistent draft workspace for multi-step reasoning, pedagogical problem-solving,
outline drafting, and iterative calculation notes. Persists to `.scratchpad.md` in the
workspace root, isolated from source repository code.

Responsibilities:
- Read current scratchpad contents (`read`).
- Overwrite scratchpad with new content (`write`).
- Append new notes or step deductions to scratchpad (`append`).
- Clear scratchpad (`clear`).
- Enforce size boundaries to prevent runaway context exhaustion.
"""

from __future__ import annotations

from pathlib import Path

from agent.tools.core.base import AgentTool

_MAX_SCRATCHPAD_CHARS = 500_000


def scratchpad_tool(workspace: str | Path) -> AgentTool:
    ws = Path(workspace)
    pad_file = ws / ".scratchpad.md"

    def scratchpad(action: str = "read", content: str = "") -> str:
        act = (action or "read").lower().strip()
        if act == "read":
            if not pad_file.exists():
                return "(演草纸当前为空)"
            try:
                text = pad_file.read_text(encoding="utf-8", errors="replace")
                return text if text.strip() else "(演草纸当前为空)"
            except OSError as exc:
                return f"[读取失败] 无法读取演草纸: {exc}"

        if act == "write":
            text_to_write = content or ""
            if len(text_to_write) > _MAX_SCRATCHPAD_CHARS:
                return f"[参数错误] 演草纸内容超过长度限制 ({_MAX_SCRATCHPAD_CHARS} 字符)。"
            try:
                pad_file.parent.mkdir(parents=True, exist_ok=True)
                pad_file.write_text(text_to_write, encoding="utf-8")
                return f"[演草纸已更新] 当前共 {len(text_to_write)} 字符"
            except OSError as exc:
                return f"[写入失败] 无法更新演草纸: {exc}"

        if act == "append":
            if not content:
                return "[演草纸未变动] 追加内容为空"
            try:
                pad_file.parent.mkdir(parents=True, exist_ok=True)
                existing = ""
                if pad_file.exists():
                    existing = pad_file.read_text(encoding="utf-8", errors="replace")
                delimiter = "\n\n" if existing and not existing.endswith("\n") else ""
                new_text = existing + delimiter + content
                if len(new_text) > _MAX_SCRATCHPAD_CHARS:
                    return (
                        f"[参数错误] 追加后演草纸总长度将超过限制 ({_MAX_SCRATCHPAD_CHARS} 字符)。"
                    )
                pad_file.write_text(new_text, encoding="utf-8")
                return f"[演草纸已追加] 当前共 {len(new_text)} 字符"
            except OSError as exc:
                return f"[追加失败] 无法追加到演草纸: {exc}"

        if act == "clear":
            try:
                if pad_file.exists():
                    pad_file.write_text("", encoding="utf-8")
                return "[演草纸已清空]"
            except OSError as exc:
                return f"[清空失败] 无法清空演草纸: {exc}"

        return f"[参数错误] scratchpad: 不支持的 action: {action} (仅支持 read/write/append/clear)"

    return AgentTool(
        name="scratchpad",
        description="用于记录中间推导、解题草稿、长文构思或分步演练的演草纸(支持 read/write/append/clear)",
        handler=scratchpad,
        dimension="plan",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型: read (读取), write (重写), append (追加), clear (清空)",
                },
                "content": {
                    "type": "string",
                    "description": "写入或追加的内容 (read 和 clear 操作无需提供)",
                },
            },
        },
    )


__all__ = ["scratchpad_tool"]
