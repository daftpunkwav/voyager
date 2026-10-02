"""bash tool: command execution in the agent working directory
(shell dimension).

Execution-time confirmation is retired; the gates in front of this tool are
the tool permission modes (deny / allow `bash:` argv prefixes) and the shell
dimension policy. This module additionally hard-blocks destructive commands
before execution — even if every configurable gate is loosened, machine-level
irreversible operations are never allowed through.

Execution uses create_subprocess_exec(argv) without shell interpretation of
pipes/redirections/globs. Windows built-in commands (dir/echo) raise
FileNotFoundError and there is no shell=True fallback. The subprocess cwd is
pinned to the agent working directory supplied at assembly time, so relative
paths land there; but this is not a chroot — absolute paths, `..`, and
interpreters on PATH can still escape that directory.

Output collection is bounded but lossless up to the global tool-result
budget: the stream is read up to a large safety ceiling (memory bound) and
anything beyond is drained and discarded while the process runs to
completion (exit code stays truthful). The invoke-layer result budget does
the truncation-with-spill, so the model can re-read the full output from
the spill file instead of losing it at a tool-local cap.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from agent.tools.core.base import AgentTool
from agent.tools.workspace.console_decode import decode_console_output

#: In-memory safety ceiling for collected output (bytes); beyond it chunks
#: are drained but discarded - the process still runs to completion so the
#: exit code stays truthful. The result budget, not this cap, decides what
#: the model sees.
_MAX_COLLECT_BYTES = 1_000_000

#: Grace period for draining the output pipe once the process is done. A
#: grandchild that inherited the stdout handle keeps the pipe open past the
#: parent's exit (and past a kill - TerminateProcess/kill never reaches
#: grandchildren), so without a bound the final drain await - and with it the
#: tool call and its deadline-cancel - would hang until the orphan exits.
_DRAIN_GRACE_S = 5.0

#: Read chunk size for the capped collector
_CHUNK = 65_536

# Explicit machine-level destructive commands (a blocklist is the last line of
# defense, not a general parser; normal development commands never match)
_DESTRUCTIVE_RE = re.compile(
    r"\bmkfs(\.\w+)?\b"  # format a filesystem
    r"|\bdd\b[^|;&]*of=/dev/(sd|nvme|vd)"  # dd straight to a disk device
    r"|\b(shutdown|halt|reboot|poweroff)\b"  # shutdown/reboot
    r"|\brm\b[^|;&]*\s-{1,2}[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(/{0,1})(\s|$)"  # rm -rf /
    r"|\brm\b[^|;&]*\s-{1,2}[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(~|\$HOME|%USERPROFILE%)"
    r"|\bformat\s+[a-z]:"  # Windows drive format
    r"|\bdiskpart\b"
    r"|\b(curl|wget)\b[^|;\n]*\|\s*(sh|bash|zsh|cmd)"
    r"|\bInvoke-Expression\b"
    r"|\bdel\s+/[sS]\s+/[qQ]\s+[cC]:\\",
    re.IGNORECASE,
)


async def _read_capped(stream: asyncio.StreamReader | None, cap: int, buf: bytearray) -> int:
    """Read the stream to EOF, appending up to `cap` bytes into the
    caller-held buffer; returns the count of bytes discarded beyond the cap.

    The buffer is filled incrementally so a forced partial drain (an orphaned
    descendant holding the pipe; see the bounded IO finish in bash()) still
    keeps whatever was captured before the grace expiry."""
    if stream is None:
        return 0
    kept = 0
    discarded = 0
    while True:
        chunk = await stream.read(_CHUNK)
        if not chunk:
            return discarded
        if kept < cap:
            take = chunk[: cap - kept]
            buf.extend(take)
            kept += len(take)
            discarded += len(chunk) - len(take)
        else:
            discarded += len(chunk)


def _resolve_windows_stub(argv0: str) -> str:
    """On Windows, `python`/`python3` from PATH often resolves to the
    Microsoft Store alias under WindowsApps - a launcher stub that hangs
    forever when spawned headlessly (no output, no exit). Prefer a real
    interpreter found elsewhere on PATH, then the running interpreter."""
    if os.name != "nt":
        return argv0
    stem = argv0.lower()
    stem = stem.removesuffix(".exe")
    if stem not in ("python", "python3"):
        return argv0
    for candidate in (argv0, "python", "python3"):
        found = shutil.which(candidate)
        if found and "windowsapps" not in found.lower():
            return found
    exe = Path(sys.executable)
    if exe.name.lower().replace(".exe", "") in ("python", "python3", "pythonw"):
        return str(exe)
    return argv0


def bash_tool(cwd: str | Path) -> AgentTool:
    """Build the bash tool; the subprocess cwd is pinned to the agent
    working directory supplied at assembly time."""
    # codeql[py/path-injection] cwd is the operator-configured agent working
    # directory from settings, resolved once at assembly to pin the subprocess
    # down; commands themselves are gated by the policy engine.
    work = Path(cwd).expanduser().resolve()

    async def bash(command: str, timeout: float = 30.0) -> str:
        if _DESTRUCTIVE_RE.search(command):
            return (
                "[已拒绝] 命令含整机级破坏操作(格式化/关机/根递归删除),"
                "已被策略硬拦截;如确需执行请在系统终端手动操作"
            )
        try:
            argv = shlex.split(command, posix=(os.name != "nt"))
        except ValueError as exc:
            return f"[已拒绝] 命令无法解析: {exc}"
        if not argv:
            return "[已拒绝] 空命令"
        if not work.is_dir():
            return (
                f"[失败] 工作目录不可用: {work} 不存在或不是目录;"
                "不会回退到进程当前目录,请让用户先修复 agent 工作目录设置"
            )
        argv[0] = _resolve_windows_stub(argv[0])
        try:
            proc = await asyncio.create_subprocess_exec(
                argv[0],
                *argv[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(work),
            )
        except FileNotFoundError:
            return (
                f"[失败] 找不到可执行文件 {argv[0]!r}。"
                "本工具不经 shell 解释,Windows 内建命令(dir/echo)请改用 "
                "解释器 -c 或给出可执行文件的完整路径。"
            )
        except OSError as exc:
            # Race: the directory was moved away / became inaccessible after the
            # check; never fall back to the process cwd by omitting cwd
            return f"[失败] 工作目录不可用: {exc}"
        buf = bytearray()
        reader = asyncio.ensure_future(_read_capped(proc.stdout, _MAX_COLLECT_BYTES, buf))
        # The process-exit future is shielded so a timeout does not consume
        # it: the bounded IO finish below still needs it.
        waiter = asyncio.ensure_future(proc.wait())
        timed_out = False
        started = time.monotonic()
        try:
            # Windows asyncio resolves proc.wait() only when the process has
            # exited AND every pipe reached EOF (transport._try_finish), so a
            # grandchild inheriting the stdout handle delays it past the
            # command's own completion. The timeout bounds that wait; the
            # returncode check afterwards separates a still-running command
            # (kill it) from a completed one whose output pipe is merely held
            # (report its real result instead of a fake timeout).
            await asyncio.wait_for(asyncio.shield(waiter), timeout)
        except TimeoutError:
            timed_out = proc.returncode is None
            if timed_out:
                proc.kill()
        except asyncio.CancelledError:
            # the calling task was cancelled (run tree cancel / shutdown):
            # never leak the child process or the reader/waiter tasks; the
            # reaping below is grace-bounded so the cancellation itself
            # cannot hang on an orphaned pipe holder
            if proc.returncode is None:
                proc.kill()
            reader.cancel()
            waiter.cancel()
            await asyncio.wait({reader, waiter}, timeout=_DRAIN_GRACE_S)
            raise
        wall = time.monotonic() - started
        # Bounded finish: an orphaned descendant holding the inherited stdout
        # handle would otherwise hang the drain (and the deadline cancel)
        # until the orphan exits on its own.
        done, pending = await asyncio.wait({reader, waiter}, timeout=_DRAIN_GRACE_S)
        for task in pending:
            task.cancel()
        discarded = reader.result() if reader in done else 0
        out = bytes(buf)
        text = decode_console_output(out)
        if discarded:
            text += (
                f"\n…[输出超出 {_MAX_COLLECT_BYTES} 字节安全上限,余量已丢弃"
                f"({discarded} 字节);进程已正常运行结束]"
            )
        if timed_out:
            body = f"\n{text}" if text else ""
            return (
                f"[超时] {timeout}s 未结束,已终止(已捕获输出如下);"
                f"若命令需要更久,可加大 timeout 参数重试{body}"
            )
        # Structured header (codex-style): exit code, wall time and captured
        # line count up front, so a truncated preview is still actionable.
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        suffix = f"\n{text}" if text else ""
        return f"exit={proc.returncode} wall={wall:.1f}s lines={lines}{suffix}"

    return AgentTool(
        name="bash",
        description=(
            "在 agent 工作目录执行命令(不经 shell;可用工具权限的 bash: 前缀规则限制;"
            "长输出会保存到文件供 read 分段查看)"
        ),
        handler=bash,
        dimension="shell",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["command"],
        },
    )


__all__ = ["bash_tool"]
