"""Dev launcher: backend (uvicorn :8000) plus web (vite :5173).

Run from the repo root: `uv run python -m host.dev`. Ctrl+C exits both.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root (packages/host/src/host)


def _stop_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree. On Windows, shell=True starts cmd.exe with
    node/npm as children; terminate() alone would leave orphans, so taskkill /T
    takes down the children too."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.terminate()


def main() -> None:
    import uvicorn

    # npm requires shell=True on Windows
    web = subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "apps" / "web", shell=True)
    try:
        uvicorn.run("host.assemble:build", factory=True, host="127.0.0.1", port=8000, reload=False)
    finally:
        _stop_tree(web)


if __name__ == "__main__":
    main()
