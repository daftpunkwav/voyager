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
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from agent.tools.core.base import AgentTool

_MAX_SCRATCHPAD_CHARS = 500_000

#: How long a caller waits for the cross-process pad lock before surfacing an
#: explicit busy result instead of hanging the tool call indefinitely.
_LOCK_TIMEOUT_SECONDS = 30.0

#: Serializes scratchpad mutations across threads in this process; the file
#: lock inside ``_scratchpad_lock`` covers the cross-process case.
_PAD_LOCK = threading.Lock()


class _ScratchpadBusy(RuntimeError):
    """Raised when the pad lock cannot be acquired within the deadline."""


if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle: IO[bytes]) -> bool:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _release_lock(handle: IO[bytes]) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle: IO[bytes]) -> bool:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _release_lock(handle: IO[bytes]) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _normalize_lf(text: str) -> str:
    """Reduce every line-ending convention to plain LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@contextmanager
def _scratchpad_lock(pad_file: Path) -> Iterator[None]:
    """Serialize the read-limit-append critical section across threads and processes.

    Acquisition is bounded: a stalled holder surfaces as ``_ScratchpadBusy``
    after the deadline instead of hanging the tool call forever.
    """
    with _PAD_LOCK:
        lock_file = pad_file.with_name(pad_file.name + ".lock")
        with lock_file.open("a+b") as handle:
            deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
            while not _try_lock(handle):
                if time.monotonic() >= deadline:
                    raise _ScratchpadBusy("pad lock held elsewhere")
                time.sleep(0.05)
            try:
                yield
            finally:
                _release_lock(handle)


def _append_locked(pad_file: Path, note: str) -> str:
    """Append ``note`` with the pad lock already held; OSError propagates.

    The previous content is inspected only to size the append and pick the
    separator; the file is extended in place instead of being round-tripped
    through a read-modify-write rewrite.
    """
    existing = ""
    if pad_file.exists():
        # raw bytes, because read_text would hide CRLF behind universal
        # newlines while the file keeps them on disk
        raw = pad_file.read_bytes()
        existing = raw.decode("utf-8", errors="replace")
    if "\r" in existing:
        # a pad created outside this tool may carry CRLF bytes; normalize
        # once so the file stays on a single line-ending convention
        existing = _normalize_lf(existing)
        with pad_file.open("r+b") as rewrite:
            rewrite.write(existing.encode("utf-8"))
            rewrite.truncate()
    needs_separator = bool(existing) and not existing.endswith("\n")
    appended = ("\n\n" if needs_separator else "") + note
    if len(existing) + len(appended) > _MAX_SCRATCHPAD_CHARS:
        return f"[参数错误] 追加后演草纸总长度将超过限制 ({_MAX_SCRATCHPAD_CHARS} 字符)。"
    start_size = pad_file.stat().st_size if pad_file.exists() else 0
    try:
        with pad_file.open("a", encoding="utf-8", newline="\n") as pad:
            pad.write(appended)
            pad.flush()
    except OSError:
        # a partial buffered write may have landed; restore the pre-append
        # size so a retry cannot leave fragments behind
        try:
            with pad_file.open("r+b") as repair:
                repair.truncate(start_size)
        except OSError:
            pass
        raise
    return f"[演草纸已追加] 当前共 {len(existing) + len(appended)} 字符"


def scratchpad_tool(workspace: str | Path) -> AgentTool:
    ws = Path(workspace)
    pad_file = ws / ".scratchpad.md"

    def scratchpad(action: str = "read", content: str = "") -> str:
        act = (action or "read").lower().strip()
        if act == "read":
            if not pad_file.exists():
                return "(演草纸当前为空)"
            try:
                # Reads take the lock too, so they never observe a pad
                # truncated mid-way by a concurrent write or clear.
                with _scratchpad_lock(pad_file):
                    text = pad_file.read_text(encoding="utf-8", errors="replace")
                return text if text.strip() else "(演草纸当前为空)"
            except _ScratchpadBusy:
                return "[演草纸忙] 演草纸正被另一进程占用，请稍后重试"
            except OSError as exc:
                return f"[读取失败] 无法读取演草纸: {exc}"

        if act == "write":
            text_to_write = _normalize_lf(content or "")
            if len(text_to_write) > _MAX_SCRATCHPAD_CHARS:
                return f"[参数错误] 演草纸内容超过长度限制 ({_MAX_SCRATCHPAD_CHARS} 字符)。"
            try:
                pad_file.parent.mkdir(parents=True, exist_ok=True)
                # A full rewrite lands normalized LF bytes on every platform,
                # so later appends never mix line-ending conventions.
                with _scratchpad_lock(pad_file):
                    pad_file.write_text(text_to_write, encoding="utf-8", newline="\n")
                return f"[演草纸已更新] 当前共 {len(text_to_write)} 字符"
            except _ScratchpadBusy:
                return "[演草纸忙] 演草纸正被另一进程占用，请稍后重试"
            except OSError as exc:
                return f"[写入失败] 无法更新演草纸: {exc}"

        if act == "append":
            if not content:
                return "[演草纸未变动] 追加内容为空"
            note = _normalize_lf(content)
            try:
                pad_file.parent.mkdir(parents=True, exist_ok=True)
                # hold the lock across the whole read → limit check → append so
                # concurrent writers always see the latest pad: no skipped
                # separator and no overshoot past the limit
                with _scratchpad_lock(pad_file):
                    result = _append_locked(pad_file, note)
                return result
            except _ScratchpadBusy:
                return "[演草纸忙] 演草纸正被另一进程占用，请稍后重试"
            except OSError as exc:
                return f"[追加失败] 无法追加到演草纸: {exc}"

        if act == "clear":
            # an absent pad is already clear; check before touching the lock
            # sidecar so a missing workspace does not turn into a failure
            if not pad_file.exists():
                return "[演草纸已清空]"
            try:
                with _scratchpad_lock(pad_file):
                    pad_file.write_text("", encoding="utf-8", newline="\n")
                return "[演草纸已清空]"
            except _ScratchpadBusy:
                return "[演草纸忙] 演草纸正被另一进程占用，请稍后重试"
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
