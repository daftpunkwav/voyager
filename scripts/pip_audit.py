"""Scan the resolved Python dependency set for known CVEs (audit:py).

pip-audit cannot run against a uv workspace directly (it rejects the
multi-package layout), so the scan targets the lockfile resolution: `uv
export` writes a flat requirements.txt (workspace members and the root
project excluded) to a temp file, and pip-audit reads that. The audit tool
itself runs via `uvx` -- ephemeral, no dev-group footprint. Exit code
propagates: nonzero when a known vulnerability is found.

Run: npm run audit:py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    with tempfile.NamedTemporaryFile(prefix="voyager-audit-", suffix=".txt", delete=False) as f:
        reqs = Path(f.name)
    try:
        export = subprocess.run(
            [
                "uv",
                "export",
                "--format",
                "requirements-txt",
                "--no-hashes",
                "--no-emit-project",
                "--no-emit-workspace",
                "-o",
                str(reqs),
            ],
            check=False,
        )
        if export.returncode != 0:
            return export.returncode
        audit = subprocess.run(["uvx", "pip-audit", "-r", str(reqs)], check=False)
        return audit.returncode
    finally:
        reqs.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
