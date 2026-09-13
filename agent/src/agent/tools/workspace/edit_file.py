"""edit_file tool: atomic in-place string replacement inside the jail.

Text files only; binary heads are refused. The write is temp-file +
os.replace so an interrupted edit never leaves a half-written target.

Matching walks a uniqueness-guarded degradation chain (edit_matchers): the
exact literal pass keeps the original semantics (count, CRLF byte-fidelity),
and only when it finds nothing does the fuzzy ladder engage. Inserted text
is aligned with the file's newline convention so CRLF files never end up
with mixed endings.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.edit_matchers import locate, reindent
from agent.tools.workspace.jail import Jail


def _to_file_newlines(text: str, new_text: str) -> str:
    """Align inserted text with the file's newline convention so a CRLF file
    does not end up with mixed endings after matching a LF old_text."""
    if "\r\n" in text and "\n" in new_text and "\r\n" not in new_text:
        return new_text.replace("\n", "\r\n")
    return new_text


def _atomic_write(target: Path, updated: str) -> None:
    # Atomic write (same discipline as TodoStore): temp file + os.replace.
    # newline="": no CRLF translation on write, so a Windows \r\n file
    # round-trips byte-identical outside the replaced span (write_text
    # would double every \r to \r\r\n).
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    os.replace(tmp, target)


def _fuzzy_edit(jail: Jail, target: Path, text: str, old_text: str, new_text: str) -> Any:
    """Apply the degradation chain after the exact pass found nothing."""
    result = locate(text, old_text)
    if result.span is None:
        if result.ambiguous:
            return (
                f"[失败] 未找到唯一匹配(模糊链发现 {result.ambiguous} 处候选): "
                "请加长 old_text 使其唯一,或用 read_file 核对原文"
            )
        return "[失败] 未找到匹配: 请用 read_file/grep 先看原文"
    start, end = result.span
    replacement = new_text
    if result.level == "line_trimmed" and result.line_indent:
        replacement = reindent(replacement, result.line_indent)
    if result.consumed_eol and not replacement.endswith(("\n", "\r\n")):
        # the span swallowed the line break old_text ended with: keep one
        replacement += "\r\n" if "\r\n" in text else "\n"
    updated = text[:start] + _to_file_newlines(text, replacement) + text[end:]
    _atomic_write(target, updated)
    return {"edited": jail.display(target), "replacements": 1, "matched_by": result.level}


def edit_file_tool(jail: Jail) -> AgentTool:
    def edit_file(path: str, old_text: str, new_text: str, count: int = 1) -> Any:
        """Atomic string replacement: the exact match must be unique (default
        count=1) so a short old_text never rewrites the wrong place; when the
        exact pass finds nothing, a fuzzy ladder (line/block/whitespace/
        indentation/escape) locates a unique candidate instead. Text files
        only."""
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
        if found == 0 and count == 1:
            return _fuzzy_edit(jail, target, text, old_text, new_text)
        if found == 0:
            return "[失败] 未找到匹配: 请用 read_file/grep 先看原文"
        if found > count:
            return (
                f"[失败] 匹配 {found} 处,超过 count={count}: 请加长 old_text 使其唯一,或增大 count"
            )
        updated = text.replace(old_text, _to_file_newlines(text, new_text), found)
        _atomic_write(target, updated)
        return {"edited": jail.display(target), "replacements": found, "matched_by": "exact"}

    return AgentTool(
        name="edit_file",
        description=(
            "在工作目录内原子替换文件片段(old_text 须唯一,多处匹配会失败;"
            "精确失配时按 行修剪/块锚点/空白归一/缩进 回填逐级模糊定位;大改用 write_file)"
        ),
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
