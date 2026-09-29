"""Dev launcher: backend (uvicorn :8000) plus web (vite :5173).

Run from the repo root: `uv run python -m host.dev`. Ctrl+C exits both.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root (packages/host/src/host)


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
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.terminate()


def main() -> None:
    import uvicorn

    web = subprocess.Popen(_npm_command(), cwd=ROOT / "apps" / "web", shell=False)
    try:
        uvicorn.run("host.assemble:build", factory=True, host="127.0.0.1", port=8000, reload=False)
    finally:
        _stop_tree(web)


if __name__ == "__main__":
    main()
