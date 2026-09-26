"""Tests for the bash tool surface: destructive-command guard, captured
output on timeout, workspace-pinned cwd, cancellation, and console decoding."""

import os
import re
import sys
from pathlib import Path

from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, fs_tools
from agent.tools.workspace import shell_tools
from agent.tools.workspace.console_decode import decode_console_output


class TestShellGuard:
    async def test_destructive_commands_blocked(self, tmp_path) -> None:
        """Machine-wrecking commands are hard-blocked before execution (even without an L2 confirm channel)."""
        bash = shell_tools(tmp_path)["bash"].handler
        for cmd in (
            "mkfs.ext4 /dev/sda1",
            "dd if=a of=/dev/sda",
            "shutdown now",
            "rm -rf /",
            "rm -rf ~",
            "format C: /q",
        ):
            out = await bash(cmd, timeout=2)
            assert "[已拒绝]" in out, cmd

    async def test_normal_command_not_blocked(self, tmp_path) -> None:
        bash = shell_tools(tmp_path)["bash"].handler
        # Not via the shell: interpreter -c avoids Windows' builtin echo; no nested quotes so shlex does not mis-split in nt mode
        out = await bash(f"{sys.executable} -c print(42)", timeout=5)
        assert "已拒绝" not in out and "42" in out

    async def test_large_output_not_tool_truncated(self, tmp_path) -> None:
        """Output beyond the old 10k tool-local cap comes back whole; the
        invoke-layer result budget (spill) decides what the model sees."""
        # a script file instead of -c quoting: nt-mode shlex keeps literal
        # quotes, which turn a -c program into a bare string expression
        script = tmp_path / "_big.py"
        script.write_text("print('x' * 50000)", encoding="utf-8")
        bash = shell_tools(tmp_path)["bash"].handler
        out = await bash(f"{sys.executable} {script.name}", timeout=15)
        # codex-style structured header: exit code, wall time, captured lines
        assert re.match(r"exit=0 wall=\d+\.\d+s lines=\d+\n", out), out
        assert "x" * 50000 in out
        assert "截断" not in out

    async def test_timeout_reports_captured_output(self, tmp_path) -> None:
        script = tmp_path / "_slow.py"
        script.write_text(
            "import time\nprint('early', flush=True)\ntime.sleep(30)\n", encoding="utf-8"
        )
        bash = shell_tools(tmp_path)["bash"].handler
        out = await bash(f"{sys.executable} {script.name}", timeout=1.5)
        assert out.startswith("[超时]")
        assert "early" in out

    async def test_missing_executable_does_not_fall_back_to_shell(self, tmp_path) -> None:
        bash = shell_tools(tmp_path)["bash"].handler
        # Not echo: /bin/echo really exists on Unix, which would mask the no-shell-fallback behavior
        out = await bash("__no_such_cmd_xyz__", timeout=5)
        assert "[失败]" in out and "找不到可执行文件" in out

    async def test_subprocess_cwd_pinned_to_workspace(self, tmp_path) -> None:
        """The subprocess cwd is pinned to the assembly directory: relative-path scripts are found,
        and relatively written files land there rather than in the process cwd or parent."""
        work = tmp_path / "ws"
        work.mkdir()
        probe = work / "_cwd_probe.py"
        probe.write_text(
            "from pathlib import Path\n"
            "Path('cwd-probe-phase35.txt').write_text('ok', encoding='utf-8')\n",
            encoding="utf-8",
        )
        bash = shell_tools(work)["bash"].handler
        stray = Path.cwd() / "cwd-probe-phase35.txt"
        try:
            out = await bash(f"{sys.executable} {probe.name}", timeout=5)
            assert "exit=0" in out, out
            assert (work / "cwd-probe-phase35.txt").read_text(encoding="utf-8") == "ok"
            assert not (tmp_path / "cwd-probe-phase35.txt").exists()  # nothing lands in the parent
            # If the implementation drops cwd=, the file lands in the process cwd and this fails
            if Path.cwd().resolve() != work.resolve():
                assert not stray.exists()
        finally:
            # Guard against a cwd=-less implementation dirtying the repo root: clean up any leftover file in the process cwd
            if stray.exists():
                stray.unlink()

    async def test_shell_skills_write_denied_by_policy(self, workdir) -> None:
        """The policy layer refuses shell writes into skills ahead of L2; nothing lands on disk."""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "bash", {"command": "echo pwn > skills/x.txt"}))
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "x.txt").exists()

    async def test_shell_readonly_skills_execute_without_confirm(self, workdir) -> None:
        """Confirm retired: read-only skills commands are not caught by the
        skills guard (a write there is still hard-rejected above) and reach
        execution without any confirm branch."""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "bash", {"command": "type skills\\keep\\SKILL.md"}))
        assert "[需确认]" not in out and "[已取消]" not in out


class TestShellCancellation:
    async def test_cancelled_bash_raises_and_returns_promptly(self, tmp_path) -> None:
        """Cancelling a running bash propagates CancelledError through the
        kill path (child killed, reader reaped) instead of leaking."""
        import asyncio

        script = tmp_path / "_hang.py"
        script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        bash = shell_tools(tmp_path)["bash"].handler
        task = asyncio.create_task(bash(f"{sys.executable} {script.name}", timeout=30))
        await asyncio.sleep(0.3)  # let the child start
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2)
            raised = False
        except asyncio.CancelledError:
            raised = True
        assert raised  # propagation preserved; child killed inside the handler


class TestConsoleDecode:
    def test_utf8_still_wins(self) -> None:
        assert decode_console_output("中文 ok\n".encode()) == "中文 ok\n"

    def test_utf16_tried_when_nul_bytes_present(self, monkeypatch) -> None:
        """UTF-16LE output (some PowerShell pipelines) must decode as UTF-16:
        GBK accepts the NUL-interleaved bytes and would return mojibake, so
        the NUL heuristic has to put UTF-16 first in the fallback chain."""
        monkeypatch.setattr(os, "name", "nt")
        raw = "exit=0\n中文输出\n".encode("utf-16-le")
        assert decode_console_output(raw) == "exit=0\n中文输出\n"

    def test_gbk_fallback_without_nul_bytes(self, monkeypatch) -> None:
        assert decode_console_output("中文 ok\n".encode("gbk")) == "中文 ok\n"

    def test_undecodable_degrades_to_replacement(self, monkeypatch) -> None:
        assert "\ufffd" in decode_console_output(b"\xff\xfe\x81\x81\x81")
