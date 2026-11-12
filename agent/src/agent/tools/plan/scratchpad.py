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

import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from agent.tools.core.base import AgentTool

_MAX_SCRATCHPAD_CHARS = 500_000

#: Serializes scratchpad mutations across threads in this process; the file
#: lock inside ``_scratchpad_lock`` covers the cross-process case.
_PAD_LOCK = threading.Lock()


if sys.platform == "win32":
    import msvcrt

    def _exclusive_lock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)

    def _release_lock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _exclusive_lock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _release_lock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _scratchpad_lock(pad_file: Path) -> Iterator[None]:
    """Serialize the read-limit-append critical section across threads and processes."""
    with _PAD_LOCK:
        lock_file = pad_file.with_name(pad_file.name + ".lock")
        with lock_file.open("a+b") as handle:
            _exclusive_lock(handle)
            try:
                yield
            finally:
                _release_lock(handle)


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
                # LF line endings on every platform so later appends never mix conventions
                with _scratchpad_lock(pad_file):
                    pad_file.write_text(text_to_write, encoding="utf-8", newline="\n")
                return f"[演草纸已更新] 当前共 {len(text_to_write)} 字符"
            except OSError as exc:
                return f"[写入失败] 无法更新演草纸: {exc}"

        if act == "append":
            if not content:
                return "[演草纸未变动] 追加内容为空"
            try:
                pad_file.parent.mkdir(parents=True, exist_ok=True)
                # Hold the lock across the whole read → limit check → append so
                # concurrent writers always see the latest pad: no skipped
                # separator and no overshoot past the limit. Inspect the
                # previous content only to size the append and pick the
                # separator; the file is extended in place instead of being
                # round-tripped through a read-modify-write rewrite.
                with _scratchpad_lock(pad_file):
                    existing_len = 0
                    needs_separator = False
                    if pad_file.exists():
                        existing = pad_file.read_text(encoding="utf-8", errors="replace")
                        existing_len = len(existing)
                        needs_separator = bool(existing) and not existing.endswith("\n")
                    appended = ("\n\n" if needs_separator else "") + content
                    if existing_len + len(appended) > _MAX_SCRATCHPAD_CHARS:
                        return f"[参数错误] 追加后演草纸总长度将超过限制 ({_MAX_SCRATCHPAD_CHARS} 字符)。"
                    with pad_file.open("a", encoding="utf-8", newline="\n") as pad:
                        pad.write(appended)
                return f"[演草纸已追加] 当前共 {existing_len + len(appended)} 字符"
            except OSError as exc:
                return f"[追加失败] 无法追加到演草纸: {exc}"

        if act == "clear":
            try:
                with _scratchpad_lock(pad_file):
                    if pad_file.exists():
                        pad_file.write_text("", encoding="utf-8", newline="\n")
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
