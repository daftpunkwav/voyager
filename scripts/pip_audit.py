"""Scan the resolved Python dependency set for known CVEs (audit:py).

pip-audit cannot run against a uv workspace directly (it rejects the
multi-package layout), so the scan targets the lockfile resolution: `uv
export` writes a flat requirements.txt (workspace members and the root
project excluded) to a temp file, and pip-audit reads that. The export
reads the committed lockfile as it is.

The audit tool runs from the locked environment as well: it lives in a
dependency group of the root project, so uv.lock covers the tool and every
dependency it pulls in. Nothing is resolved at run time, and a compromised
release cannot enter the scan. Exit code propagates: nonzero when a known
vulnerability is found.

Run: npm run audit:py
"""

from __future__ import annotations

import subprocess  # nosec B404  # pip-audit invocation is the purpose of this script
import sys
import tempfile
from pathlib import Path

# Dependency group holding the audit tool (root pyproject.toml).
AUDIT_GROUP = "audit"


def main() -> int:
    with tempfile.NamedTemporaryFile(prefix="voyager-audit-", suffix=".txt", delete=False) as f:
        reqs = Path(f.name)
    try:
        export = subprocess.run(  # nosec B603 B607  # constant argv, dev script
            [
                "uv",
                "export",
                "--format",
                "requirements-txt",
                "--no-hashes",
                "--no-emit-project",
                "--no-emit-workspace",
                "--locked",
                "-o",
                str(reqs),
            ],
            check=False,
        )
        if export.returncode != 0:
            return export.returncode
        # The tool and its dependencies come from uv.lock: the group installs
        # exactly the versions the lockfile resolved.
        audit = subprocess.run(  # nosec B603 B607  # constant argv, dev script
            [
                "uv",
                "run",
                "--locked",
                "--no-build",
                "--group",
                AUDIT_GROUP,
                "pip-audit",
                "-r",
                str(reqs),
            ],
            check=False,
        )
        return audit.returncode
    finally:
        reqs.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
