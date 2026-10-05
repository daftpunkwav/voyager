"""Dev launcher: backend (uvicorn :8000) plus web (vite :5173).

Run from the repo root: `uv run python -m host.dev`. Ctrl+C exits both.

Single-instance guard: a second backend against the same data/runtime would
double-run the durable queue/cron jobs and race the same SQLite files, so
the launcher takes an OS-owned lock file (released automatically when the
process dies — no stale-lockfile cleanup exists). Direct
`uvicorn host.assemble:build` runs bypass this guard.
"""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404  # subprocess is the purpose of the dev launcher
import sys
from typing import IO

from platform_contracts import repo_root

ROOT = repo_root()

_LOCK_HANDLE: IO[str] | None = None  # held until process exit: closing it releases the lock


def _acquire_instance_lock() -> None:
    """Take an exclusive non-blocking lock on data/runtime/host.lock, or exit
    with a clear message when another instance holds it."""
    global _LOCK_HANDLE
    lock_path = ROOT / "data" / "runtime" / "host.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")  # noqa: SIM115  # held until process exit on purpose
    try:
        # Lock byte 0 in every instance: append mode starts at EOF and
        # msvcrt.locking is byte-range-based (fcntl.flock is whole-file), so
        # locking at EOF would let a second instance lock a non-overlapping
        # byte and sail past the guard.
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SystemExit(f"another host.dev instance is already running (lock: {lock_path})")
    handle.seek(0)
    handle.truncate()
    handle.write(f"host.dev pid={os.getpid()}\n")
    handle.flush()
    _LOCK_HANDLE = handle


def _npm_command() -> list[str]:
    """The npm executable as an argv list: on Windows npm is npm.cmd, which
    CreateProcess only launches as a real file path (never via PATH
    resolution alone), so resolve it up front. argv stays constant, so no
    shell is involved anywhere."""
    return [shutil.which("npm") or "npm", "run", "dev"]


def _stop_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree. On Windows the vite dev server runs as
    node with tooling children (esbuild etc.); terminate() alone would leave
    orphans, so taskkill /T takes down the children too."""
    if sys.platform == "win32":
        subprocess.run(  # nosec B603 B607  # constant argv, pid of our own child
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.terminate()


def main() -> None:
    import uvicorn

    _acquire_instance_lock()
    web = subprocess.Popen(_npm_command(), cwd=ROOT / "apps" / "web", shell=False)
    try:
        uvicorn.run("host.assemble:build", factory=True, host="127.0.0.1", port=8000, reload=False)
    finally:
        _stop_tree(web)


if __name__ == "__main__":
    main()
