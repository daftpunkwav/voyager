"""Scan the resolved Python dependency set for known CVEs (audit:py).

pip-audit cannot run against a uv workspace directly (it rejects the
multi-package layout), so the scan targets the lockfile resolution: `uv
export` writes a flat requirements.txt (workspace members and the root
project excluded) to a temp file, and pip-audit reads that. The export
reads the committed lockfile as it is, so the scanned set is the
resolution this repository ships.

The audit tool runs in a project of its own (tools/audit), which is
excluded from the workspace: its environment holds the audit tool and the
dependencies it pulls in, never the application dependencies and never
the default dev group. The tool is pinned in that project's dependency
group, so the project's own lockfile covers it and everything it pulls in.
Nothing is resolved at run time, and a compromised release cannot enter
the scan. Exit code propagates: nonzero when a known vulnerability is
found.

Run: npm run audit:py
"""

from __future__ import annotations

import subprocess  # nosec B404  # pip-audit invocation is the purpose of this script
import sys
import tempfile
from pathlib import Path

# The audit project: a standalone uv project outside the workspace, so the
# tool runs without the application dependencies (tools/audit/pyproject.toml).
AUDIT_PROJECT = "tools/audit"
# Dependency group holding the audit tool (audit project manifest).
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
        # The tool and its dependencies come from the audit project's
        # lockfile: the group installs exactly the versions that lockfile
        # resolved, and nothing else.
        audit = subprocess.run(  # nosec B603 B607  # constant argv, dev script
            [
                "uv",
                "run",
                "--project",
                AUDIT_PROJECT,
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
