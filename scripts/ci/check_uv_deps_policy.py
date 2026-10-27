"""Dependency policy check (uv side): fail on any banned package recorded in
a committed uv lockfile. Scans the lockfile's [[package]] entries
(name = "..."), so a ban blocks every path of arrival - direct or transitive
- without needing an installed environment. Names are PEP 503 normalized
before comparison.

Every committed lockfile is scanned, not just the root one: the audit tool
lives in a project of its own, and a ban must hold for its lockfile too."""

from __future__ import annotations

import json
import os
import re
import subprocess  # nosec B404  # git invocation is the purpose of this check
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = Path(__file__).resolve().parent / "dependency-policy.json"


def canonical(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of -/_/. collapsed to one dash."""
    return re.sub(r"[-_.]+", "-", name).lower()


def lockfiles() -> list[Path]:
    """The committed uv lockfiles of the repository.

    The list comes from the git index, so a lockfile that was never
    committed cannot decide the verdict - and a lockfile that was committed
    always can, wherever in the tree it lives.

    The listing is NUL-delimited and read as bytes: git quotes non-ASCII
    paths in its default output, and a quoted path would no longer look like
    a lockfile. The bytes are decoded the way a filesystem path is, so the
    returned path is the one git knows.
    """
    listed = subprocess.run(  # nosec B603 B607  # constant argv, dev script
        ["git", "-C", str(ROOT), "ls-files", "--full-name", "-z"],
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        print(
            f"cannot list the committed files: {listed.stderr.decode(errors='replace').strip()}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    names = [
        name
        for name in (os.fsdecode(entry) for entry in listed.stdout.split(b"\0"))
        if name == "uv.lock" or name.endswith("/uv.lock")
    ]
    return [ROOT / name for name in sorted(names)]


def installed_packages(lock: Path) -> dict[str, str]:
    """The distributions a lockfile resolves, canonical name -> version.

    Normalize line endings and parse [[package]] blocks field-order-free:
    uv's lockfile layout is not a contract, only the field names are.
    """
    text = lock.read_text(encoding="utf-8").replace("\r\n", "\n")
    installed: dict[str, str] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'^\s*name\s*=\s*"([^"]+)"', block, re.MULTILINE)
        version = re.search(r'^\s*version\s*=\s*"([^"]+)"', block, re.MULTILINE)
        if name:
            installed[canonical(name.group(1))] = version.group(1) if version else ""
    return installed


def main() -> int:
    """Fail on any banned distribution present in a committed uv lockfile."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    banned = {canonical(name): reason for name, reason in policy.get("pip", {}).items()}
    if not banned:
        print("pip dependency policy ok (empty denylist)")
        return 0

    locks = lockfiles()
    if not locks:
        print("no committed uv lockfile found - nothing scanned?", file=sys.stderr)
        return 1

    # A distribution may appear in several lockfiles; the first one that
    # resolves it names the source of the finding.
    installed: dict[str, tuple[str, str]] = {}
    for lock in locks:
        packages = installed_packages(lock)
        if not packages:
            print(f"no packages parsed from {lock.name} - parse failure?", file=sys.stderr)
            return 1
        source = lock.relative_to(ROOT).as_posix()
        for name, version in packages.items():
            installed.setdefault(name, (version, source))

    violations = sorted(name for name in installed if name in banned)
    if violations:
        print("banned pip dependencies present:")
        for name in violations:
            version, source = installed[name]
            print(f"  - {name} {version} ({source}): {banned[name]}")
        return 1
    print(f"pip dependency policy ok ({len(installed)} packages scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
