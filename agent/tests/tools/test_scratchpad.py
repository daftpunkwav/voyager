"""Tests for the task scratchpad tool."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING

import agent.tools.plan.scratchpad as scratchpad_module
import pytest
from agent.tools.plan.scratchpad import _MAX_SCRATCHPAD_CHARS, scratchpad_tool

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

LOCK_SIDECAR = ".scratchpad.md.lock"


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def force_overlap(monkeypatch: pytest.MonkeyPatch, parties: int) -> None:
    """Make concurrent handlers meet at the lock entrance before proceeding.

    Without this the scheduler may run each append serially, which would let
    the concurrency assertions pass even without any synchronization.
    """
    real_lock = scratchpad_module._scratchpad_lock
    gate = threading.Barrier(parties, timeout=5)

    def gated_lock(pad_file: Path) -> AbstractContextManager[None]:
        gate.wait()
        return real_lock(pad_file)

    monkeypatch.setattr(scratchpad_module, "_scratchpad_lock", gated_lock)


class TestScratchpad:
    def test_read_empty_scratchpad(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        result = tool.handler(action="read")
        assert result == "(演草纸当前为空)"

    def test_write_and_read(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        write_res = tool.handler(action="write", content="步骤 1: 概念引入\n步骤 2: 编写测试")
        assert "[演草纸已更新]" in write_res

        read_res = tool.handler(action="read")
        assert "步骤 1: 概念引入" in read_res
        assert "步骤 2: 编写测试" in read_res

    def test_append_content(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="初始想法")
        append_res = tool.handler(action="append", content="补充思路")
        assert "[演草纸已追加]" in append_res

        read_res = tool.handler(action="read")
        assert "初始想法" in read_res
        assert "补充思路" in read_res
        # a pad not ending in a newline gets the blank-line separator
        assert read_res == "初始想法\n\n补充思路"

    def test_append_crossing_limit_is_rejected(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        existing = "记" * (_MAX_SCRATCHPAD_CHARS - 10)
        tool.handler(action="write", content=existing)

        append_res = tool.handler(action="append", content="补" * 20)
        assert "[参数错误]" in append_res
        assert "超过限制" in append_res

        # the pad must be untouched by a rejected append
        assert tool.handler(action="read") == existing

    def test_append_writes_lf_line_endings(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="第一段\n")
        tool.handler(action="append", content="第二段\n")

        raw = (workspace / ".scratchpad.md").read_bytes()
        # every writer keeps the pad on LF so appends never mix line-ending conventions
        assert b"\r" not in raw
        assert raw.endswith("第二段\n".encode())

    def test_write_normalizes_crlf_content(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="一\r\n二")

        raw = (workspace / ".scratchpad.md").read_bytes()
        assert raw == "一\n二".encode()

    def test_append_normalizes_crlf_pad(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        # a pad created outside this tool carries CRLF bytes
        (workspace / ".scratchpad.md").write_bytes("旧\r\n内容".encode())

        tool.handler(action="append", content="新行\r\n二")

        expected = "旧\n内容\n\n新行\n二"
        assert (workspace / ".scratchpad.md").read_bytes() == expected.encode()
        assert tool.handler(action="read") == expected
        # the normalization temp file must not survive the replace
        assert not (workspace / ".scratchpad.md.norm").exists()

    def test_append_serializes_concurrent_writers(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        # leave room for exactly one more 20-char note: stale readers would let all through
        tool.handler(action="write", content="记" * (_MAX_SCRATCHPAD_CHARS - 25))
        force_overlap(monkeypatch, parties=4)

        def append_note(note: str) -> str:
            return tool.handler(action="append", content=note * 20)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(append_note, ["补", "注", "稿", "笺"]))
        # release the gate so plain reads afterwards don't wait on the barrier
        monkeypatch.undo()

        assert sum("已追加" in res for res in results) == 1
        assert sum("参数错误" in res for res in results) == 3
        final = tool.handler(action="read")
        assert len(final) <= _MAX_SCRATCHPAD_CHARS

    def test_busy_lock_returns_explicit_busy_result(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有内容")
        lock_handle = (workspace / LOCK_SIDECAR).open("a+b")
        assert scratchpad_module._try_lock(lock_handle)
        monkeypatch.setattr(scratchpad_module, "_LOCK_TIMEOUT_SECONDS", 0.05)

        try:
            res = tool.handler(action="append", content="新笔记")
        finally:
            scratchpad_module._release_lock(lock_handle)
            lock_handle.close()

        assert "演草纸忙" in res
        # the timed-out append must not have touched the pad
        assert tool.handler(action="read") == "已有内容"

    def test_same_process_contention_respects_deadline(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(scratchpad_module, "_LOCK_TIMEOUT_SECONDS", 0.1)
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有内容")
        pad_lock = scratchpad_module._process_lock_for(workspace / ".scratchpad.md")
        assert pad_lock.acquire()

        try:
            res = tool.handler(action="append", content="新笔记")
        finally:
            pad_lock.release()

        assert "演草纸忙" in res
        assert tool.handler(action="read") == "已有内容"

    def test_process_locks_are_per_workspace(self, tmp_path: Path) -> None:
        first = scratchpad_module._process_lock_for(tmp_path / "a" / ".scratchpad.md")
        second = scratchpad_module._process_lock_for(tmp_path / "b" / ".scratchpad.md")
        assert first is not second
        assert first is scratchpad_module._process_lock_for(tmp_path / "a" / ".scratchpad.md")

    def test_append_rolls_back_fragment_on_write_failure(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有")

        real_open: Callable[..., Any] = Path.open

        def failing_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            handle = real_open(self, mode, *args, **kwargs)
            if mode == "a" and self.name == ".scratchpad.md":
                original_write = handle.write

                def broken_write(data: str) -> int:
                    original_write(data[:2])  # a fragment lands, then the FS fails
                    raise OSError(28, "simulated ENOSPC")

                handle.write = broken_write  # type: ignore[method-assign]
            return handle

        monkeypatch.setattr(Path, "open", failing_open)
        res = tool.handler(action="append", content="后续内容")
        monkeypatch.undo()

        assert "追加失败" in res
        # the fragment left by the partial write must not survive
        assert tool.handler(action="read") == "已有"

    def test_clear_absent_pad_is_success(self, tmp_path: Path) -> None:
        missing_ws = tmp_path / "not-created"
        tool = scratchpad_tool(missing_ws)
        assert tool.handler(action="clear") == "[演草纸已清空]"
        # an absent pad must not leave a lock sidecar behind
        assert not (missing_ws / LOCK_SIDECAR).exists()

    def test_append_empty_content(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        append_res = tool.handler(action="append", content="")
        assert "[演草纸未变动]" in append_res

    def test_clear_scratchpad(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="临时记录")
        clear_res = tool.handler(action="clear")
        assert "[演草纸已清空]" in clear_res

        read_res = tool.handler(action="read")
        assert read_res == "(演草纸当前为空)"

    def test_invalid_action(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        res = tool.handler(action="dance")
        assert "[参数错误]" in res
        assert "不支持的 action" in res
