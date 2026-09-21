"""code-exec executor: container first, host-process fallback
without docker.

Responsibilities:
- Run one-shot executions: one-shot docker container when available,
  restricted host subprocess as fallback (known interpreters only)
- Mount the artifact directory and apply timeout / memory / network switch
- Whitelist-validate runtime config (image, command tokens, file extension)
  before execution

The artifact directory (workspace/sandbox/artifacts/<exec_id>/, mounted as
/workspace inside the container) and the network is off by
default. Executions are one-shot with no persisted environment state. Runtime
config comes from settings (data side) and always passes whitelist validation
before execution, preventing config from injecting execution parameters.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "code-exec"

# Whitelist for image names / command tokens: covers docker references and
# common argument characters, explicitly excluding whitespace and shell/
# injection metacharacters such as ;|$`&()<>
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]*$")
_CMD_TOKEN_RE = re.compile(r"^[A-Za-z0-9._/@:=,+-]+$")
_EXT_RE = re.compile(r"^\.[A-Za-z0-9]{1,10}$")

# Host fallback allows only known interpreters; custom runtimes require docker.
_HOST_INTERPRETERS: dict[str, list[str]] = {
    "python": ["python"],
    "node": ["node"],
    "shell": ["bash"],
}


def _validate_runtime(runtime: dict[str, Any]) -> None:
    """Validate runtime config fields; any invalid value rejects execution
    with INVALID_INPUT."""
    image = str(runtime.get("image") or "")
    if not _IMAGE_RE.match(image):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid runtime image name: {image!r}"
        )
    cmd = runtime.get("cmd")
    if (
        not isinstance(cmd, list)
        or not cmd
        or not all(isinstance(c, str) and _CMD_TOKEN_RE.match(c) for c in cmd)
    ):
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid runtime command list: {cmd!r}"
        )
    ext = str(runtime.get("file_ext") or "")
    if not _EXT_RE.match(ext):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid file extension: {ext!r}")


@dataclass
class RunResult:
    """Execution result: exit code, output streams, artifact directory."""

    status: str
    exit_code: int
    stdout: str
    stderr: str
    artifact_dir: str


#: Per-stream retained output cap. Output past the cap is still drained
#: (and discarded) so a chatty child never blocks on a full pipe; only what
#: is kept -- and later stored / emitted -- is bounded.
_MAX_OUTPUT_BYTES = 1024 * 1024
_TRUNCATED_MARK = "\n...[output truncated]"


async def _read_capped(stream: asyncio.StreamReader) -> bytes:
    """Read one output pipe to EOF, keeping at most _MAX_OUTPUT_BYTES.

    Draining continues past the cap (discarding the excess): stopping the
    reads instead would let the child block forever on a full pipe while
    the parent waits for it to exit.
    """
    buf = bytearray()
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        if len(buf) <= _MAX_OUTPUT_BYTES:
            buf.extend(chunk)
    if len(buf) > _MAX_OUTPUT_BYTES:
        return bytes(buf[:_MAX_OUTPUT_BYTES]) + _TRUNCATED_MARK.encode()
    return bytes(buf)


async def _collect(proc: asyncio.subprocess.Process) -> tuple[bytes, bytes]:
    """Read both pipes concurrently to EOF (retention bounded per stream)."""
    if proc.stdout is None or proc.stderr is None:  # unreachable: both are PIPE
        raise RuntimeError("subprocess was not created with piped output")
    out_task = asyncio.create_task(_read_capped(proc.stdout))
    err_task = asyncio.create_task(_read_capped(proc.stderr))
    # gather cancels both readers when this await is cancelled (the timeout
    # path), so no reader task outlives _collect
    out, err = await asyncio.gather(out_task, err_task)
    return out, err


async def _finish(proc: asyncio.subprocess.Process) -> tuple[bytes, bytes]:
    """Read pipes to EOF, then reap the child.

    Pipes can reach EOF before the process exits: a child may close or
    redirect its descriptors and keep running. Waiting for the child after
    the reads keeps the exit code accurate, prevents a daemonized child from
    escaping the timeout envelope, and avoids "subprocess still running"
    noise when the handle is garbage-collected.
    """
    out, err = await _collect(proc)
    await proc.wait()
    return out, err


async def _execute(
    args: list[str],
    *,
    artifact_dir: Path,
    cwd: Path | None,
    timeout: int,
    stderr_prefix: str = "",
) -> RunResult:
    """Run one subprocess under the shared output/timeout discipline."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd is not None else None,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(_finish(proc), timeout=timeout)
    except TimeoutError:
        proc.kill()
        # Reap the killed child; without this the process handle lingers
        # until garbage collection
        await proc.wait()
        return RunResult(
            status="timeout",
            exit_code=-1,
            stdout="",
            stderr="execution timed out",
            artifact_dir=str(artifact_dir),
        )
    return RunResult(
        status="completed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode or 0,
        stdout=stdout_b.decode(errors="replace"),
        stderr=stderr_prefix + stderr_b.decode(errors="replace"),
        artifact_dir=str(artifact_dir),
    )


async def run_in_runtime(
    runtime: dict[str, Any],
    code: str,
    *,
    timeout: int,
    memory_mb: int,
    network: bool,
    use_host_fallback: bool,
    workspace: Path,
) -> RunResult:
    """Run a code snippet per the runtime config.

    The container sandbox is the intended final form. Current behavior:
    - with docker available, run a one-shot container;
    - otherwise, when use_host_fallback=True, spawn a restricted host
      subprocess (meant for dev/test) and print a stderr warning that
      production should enable containers.
    """
    _validate_runtime(runtime)
    exec_id = uuid.uuid4().hex[:12]
    artifact_dir = workspace / "sandbox" / "artifacts" / exec_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    ext = runtime.get("file_ext", ".txt")
    src = artifact_dir / f"main{ext}"
    src.write_text(code, encoding="utf-8")

    has_docker = shutil.which("docker") is not None
    if has_docker:
        return await _run_docker(
            runtime,
            src,
            artifact_dir,
            timeout=timeout,
            memory_mb=memory_mb,
            network=network,
        )
    if use_host_fallback:
        return await _run_host(runtime, src, artifact_dir, timeout=timeout)
    return RunResult(
        status="failed",
        exit_code=-1,
        stdout="",
        stderr="docker unavailable and host fallback disabled; cannot execute code",
        artifact_dir=str(artifact_dir),
    )


async def _run_docker(
    runtime: dict[str, Any],
    src: Path,
    artifact_dir: Path,
    *,
    timeout: int,
    memory_mb: int,
    network: bool,
) -> RunResult:
    image = runtime["image"]
    cmd = runtime.get("cmd", [])
    args = [
        "docker",
        "run",
        "--rm",
        "--network",
        "host" if network else "none",
        "-m",
        f"{memory_mb}m",
        "-v",
        f"{artifact_dir}:/workspace",
        "-w",
        "/workspace",
        image,
        *cmd,
        "main" + src.suffix,
    ]
    return await _execute(args, artifact_dir=artifact_dir, cwd=None, timeout=timeout)


async def _run_host(
    runtime: dict[str, Any],
    src: Path,
    artifact_dir: Path,
    *,
    timeout: int,
) -> RunResult:
    interpreter = str(runtime.get("id") or "")
    args = _HOST_INTERPRETERS.get(interpreter)
    if args is None:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"Host fallback only supports {'/'.join(_HOST_INTERPRETERS)} runtimes"
            f"(custom runtimes require docker): {interpreter}",
        )
    args = [*args, str(src)]
    warning = (
        "WARN: currently executing via host-process fallback, container sandbox "
        "not enabled; install docker for production and disable the host fallback.\n"
    )
    return await _execute(
        args,
        artifact_dir=artifact_dir,
        cwd=artifact_dir,
        timeout=timeout,
        stderr_prefix=warning,
    )
