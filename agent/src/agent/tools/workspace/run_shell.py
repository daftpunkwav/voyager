"""run_shell tool: command execution in the agent working directory
(shell dimension, L2 confirm by default).

L2 confirmation is the main gate; this module additionally hard-blocks
destructive commands before execution — even if the confirm channel is
bypassed (subtasks without confirm / future refactoring), machine-level
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
from pathlib import Path

from agent.tools.core.base import AgentTool

#: In-memory safety ceiling for collected output (bytes); beyond it chunks
#: are drained but discarded - the process still runs to completion so the
#: exit code stays truthful. The result budget, not this cap, decides what
#: the model sees.
_MAX_COLLECT_BYTES = 1_000_000

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


async def _read_capped(stream: asyncio.StreamReader | None, cap: int) -> tuple[bytes, int]:
    """Read the stream to EOF, keeping at most `cap` bytes; returns the kept
    bytes and how many bytes were discarded beyond the cap."""
    if stream is None:
        return b"", 0
    kept: list[bytes] = []
    total = 0
    discarded = 0
    while True:
        chunk = await stream.read(_CHUNK)
        if not chunk:
            return b"".join(kept), discarded
        if total < cap:
            keep = chunk[: cap - total]
            kept.append(keep)
            total += len(keep)
            discarded += len(chunk) - len(keep)
        else:
            discarded += len(chunk)


def run_shell_tool(cwd: str | Path) -> AgentTool:
    """Build the run_shell tool; the subprocess cwd is pinned to the agent
    working directory supplied at assembly time."""
    work = Path(cwd).expanduser().resolve()

    async def run_shell(command: str, timeout: float = 30.0) -> str:
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
        reader = asyncio.ensure_future(_read_capped(proc.stdout, _MAX_COLLECT_BYTES))
        timed_out = False
        try:
            await asyncio.wait_for(proc.wait(), timeout)
        except TimeoutError:
            timed_out = True
            proc.kill()
            try:
                await proc.wait()
            except Exception:  # noqa: BLE001, S110  # best-effort reaping; timeout semantics kept
                pass
        out, discarded = await reader
        text = out.decode("utf-8", errors="replace")
        if discarded:
            text += (
                f"\n…[输出超出 {_MAX_COLLECT_BYTES} 字节安全上限,余量已丢弃"
                f"({discarded} 字节);进程已正常运行结束]"
            )
        if timed_out:
            body = f"\n{text}" if text else ""
            return f"[超时] {timeout}s 未结束,已终止(已捕获输出如下){body}"
        suffix = f"\n{text}" if text else ""
        return f"exit={proc.returncode}{suffix}"

    return AgentTool(
        name="run_shell",
        description=(
            "在 agent 工作目录执行命令(不经 shell;默认需用户确认;"
            "长输出会保存到文件供 read_file 分段查看)"
        ),
        handler=run_shell,
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


__all__ = ["run_shell_tool"]
