"""Scan the resolved Python dependency sets for known CVEs (audit:py).

pip-audit cannot run against a uv workspace directly (it rejects the
multi-package layout), so the scan targets the lockfile resolutions: `uv
export` writes flat requirements.txt files (workspace members and the
root project excluded) to a temp directory, and pip-audit reads them.
The exports read the committed lockfiles as they are, so the scanned sets
are the resolutions this repository ships.

Two sets are scanned. The application set is the resolution of the root
lockfile. The tooling set is the locked dependency set of the audit
project itself: the audit tooling runs while the scan runs, so a
vulnerability in it is reachable during the scan and has to be reported
like a vulnerability in any other dependency.

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
    with tempfile.TemporaryDirectory(prefix="voyager-audit-") as workdir:
        application = Path(workdir) / "application.txt"
        tooling = Path(workdir) / "tooling.txt"

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
                str(application),
            ],
            check=False,
        )
        if export.returncode != 0:
            return export.returncode

        # The audit tooling is a dependency set of its own, and it runs
        # during the scan: it is exported from the lockfile of the audit
        # project, so the scan covers the tooling it executes.
        export = subprocess.run(  # nosec B603 B607  # constant argv, dev script
            [
                "uv",
                "export",
                "--project",
                AUDIT_PROJECT,
                "--group",
                AUDIT_GROUP,
                "--format",
                "requirements-txt",
                "--no-hashes",
                "--no-emit-project",
                "--locked",
                "-o",
                str(tooling),
            ],
            check=False,
        )
        if export.returncode != 0:
            return export.returncode

        # The tool and its dependencies come from the audit project's
        # lockfile: the group installs exactly the versions that lockfile
        # resolved, and nothing else. Both sets are scanned separately, so
        # a package that both sets resolve never ends up pinned twice in
        # one requirement file.
        application_audit = subprocess.run(  # nosec B603 B607  # constant argv, dev script
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
                str(application),
            ],
            check=False,
        )
        tooling_audit = subprocess.run(  # nosec B603 B607  # constant argv, dev script
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
                str(tooling),
            ],
            check=False,
        )
        return application_audit.returncode or tooling_audit.returncode


if __name__ == "__main__":
    sys.exit(main())
