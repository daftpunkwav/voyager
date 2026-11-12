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


def fail_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make os.replace fail so atomic-swap error paths can be exercised."""

    def broken_replace(src: object, dst: object, *args: object, **kwargs: object) -> None:
        raise OSError(5, "simulated replace failure")

    monkeypatch.setattr(scratchpad_module.os, "replace", broken_replace)


def force_overlap(monkeypatch: pytest.MonkeyPatch, parties: int) -> dict[str, int]:
    """Make concurrent handlers meet at the lock entrance before proceeding.

    Without this the scheduler may run each append serially, which would let
    the concurrency assertions pass even without any synchronization. The
    returned counter records how many handlers actually reached the gate, so
    the test can prove the barrier was exercised at all.
    """
    real_lock = scratchpad_module._scratchpad_lock
    gate = threading.Barrier(parties, timeout=5)
    arrivals = {"n": 0}
    counter_guard = threading.Lock()

    def gated_lock(pad_file: Path) -> AbstractContextManager[None]:
        with counter_guard:
            arrivals["n"] += 1
        gate.wait()
        return real_lock(pad_file)

    monkeypatch.setattr(scratchpad_module, "_scratchpad_lock", gated_lock)
    return arrivals


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
        # no normalization temp file (unique names) may survive the replace
        assert not list(workspace.glob("*.norm"))

    def test_append_serializes_concurrent_writers(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        # leave room for exactly one more 20-char note: stale readers would let all through
        tool.handler(action="write", content="记" * (_MAX_SCRATCHPAD_CHARS - 25))
        arrivals = force_overlap(monkeypatch, parties=4)

        notes = ["补", "注", "稿", "笺"]

        def append_note(note: str) -> str:
            return tool.handler(action="append", content=note * 20)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(append_note, notes))
        # release the gate so plain reads afterwards don't wait on the barrier
        monkeypatch.undo()

        # the barrier must actually have been reached: if the append path ever
        # stops acquiring the lock, the gate never fills and this fails
        assert arrivals["n"] == 4
        assert sum("已追加" in res for res in results) == 1
        assert sum("参数错误" in res for res in results) == 3
        final = tool.handler(action="read")
        assert len(final) <= _MAX_SCRATCHPAD_CHARS
        # the one success reported must be the one note actually persisted
        persisted = [note for note in notes if note * 20 in final]
        assert len(persisted) == 1

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

    def test_read_and_clear_report_busy_and_leave_pad_intact(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有内容")
        lock_handle = (workspace / LOCK_SIDECAR).open("a+b")
        assert scratchpad_module._try_lock(lock_handle)
        monkeypatch.setattr(scratchpad_module, "_LOCK_TIMEOUT_SECONDS", 0.05)

        try:
            read_res = tool.handler(action="read")
            clear_res = tool.handler(action="clear")
        finally:
            scratchpad_module._release_lock(lock_handle)
            lock_handle.close()

        assert "演草纸忙" in read_res
        assert "演草纸忙" in clear_res
        # neither the blocked read nor the blocked clear changed the pad
        assert tool.handler(action="read") == "已有内容"

    def test_read_degrades_to_unlocked_when_sidecar_unwritable(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有内容")
        # make the sidecar path impossible to open: a directory in its place
        (workspace / LOCK_SIDECAR).unlink()
        (workspace / LOCK_SIDECAR).mkdir()

        assert tool.handler(action="read") == "已有内容"

    def test_symlink_pad_and_target_share_lock_identity(self, workspace: Path) -> None:
        target = workspace / "real-pad.md"
        target.write_text("通过目标\n", encoding="utf-8")
        link = workspace / ".scratchpad.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlink creation unavailable on this platform")

        tool = scratchpad_tool(workspace)
        append_res = tool.handler(action="append", content="通过链接")
        assert "[演草纸已追加]" in append_res

        # both access paths resolve to one lock identity, and the note lands
        # in the linked target rather than replacing the link
        assert scratchpad_module._process_lock_for(link) is scratchpad_module._process_lock_for(
            target
        )
        assert link.is_symlink()
        final = target.read_text(encoding="utf-8")
        assert "通过目标" in final
        assert "通过链接" in final

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

    def test_write_failure_keeps_pad_and_cleans_temp(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="已有内容")
        fail_replace(monkeypatch)

        res = tool.handler(action="write", content="新内容")
        monkeypatch.undo()

        assert "写入失败" in res
        # the pad is untouched and the temp file did not survive the failure
        assert tool.handler(action="read") == "已有内容"
        assert not list(workspace.glob("*.norm"))

    def test_append_normalization_failure_keeps_pad(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tool = scratchpad_tool(workspace)
        (workspace / ".scratchpad.md").write_bytes("旧\r\n内容".encode())
        fail_replace(monkeypatch)

        res = tool.handler(action="append", content="新笔记")
        monkeypatch.undo()

        assert "追加失败" in res
        # the untouched pad keeps its original CRLF bytes
        assert (workspace / ".scratchpad.md").read_bytes() == "旧\r\n内容".encode()
        assert not list(workspace.glob("*.norm"))

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
