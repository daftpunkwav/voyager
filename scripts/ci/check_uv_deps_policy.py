"""Dependency policy check (uv side): fail on any banned package recorded in
uv.lock. Scans the lockfile's [[package]] entries (name = "..."), so a ban
blocks every path of arrival - direct or transitive - without needing an
installed environment. Names are PEP 503 normalized before comparison."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "uv.lock"
POLICY = Path(__file__).resolve().parent / "dependency-policy.json"


def canonical(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of -/_/. collapsed to one dash."""
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    """Fail on any banned distribution present in uv.lock."""
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    banned = {canonical(name): reason for name, reason in policy.get("pip", {}).items()}
    if not banned:
        print("pip dependency policy ok (empty denylist)")
        return 0

    text = LOCK.read_text(encoding="utf-8")
    installed: dict[str, str] = {}
    for match in re.finditer(r'^\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text, re.M):
        installed[canonical(match.group(1))] = match.group(2)
    if not installed:
        print("no packages parsed from uv.lock - parse failure?", file=sys.stderr)
        return 1

    violations = sorted(name for name in installed if name in banned)
    if violations:
        print("banned pip dependencies present:")
        for name in violations:
            print(f"  - {name} {installed[name]}: {banned[name]}")
        return 1
    print(f"pip dependency policy ok ({len(installed)} packages scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
