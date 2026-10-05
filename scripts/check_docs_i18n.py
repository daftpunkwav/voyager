"""Verify the bilingual-documentation consistency records under docs/.

Every `docs/**/*.i18n.yaml` maps a document path to the git blob hash of
its last confirmed-consistent state (the pairing contract lives in
docs/i18n/README.md). This script re-computes each recorded hash and
fails on:

- drift: a file's current blob hash differs from the recorded one —
  the pair was edited without re-recording, or only one side moved;
- ghosts: recorded paths that no longer exist on disk;
- strays: markdown files under docs/ that no registry covers (checked
  against an explicit allowlist so genuinely unpaired files must opt
  out by name, not by omission).

Hashes are computed by shelling out to `git hash-object` so clean
filters (eol attributes, autocrlf) apply exactly as they do for the
contributor workflow the contract prescribes.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # git invocation is the purpose of this check
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ENTRY_RE = re.compile(r"^(?P<path>[^:\s]+\.md):\s*(?P<hash>[0-9a-f]{40})\s*$")

# Documents that legitimately live outside the pairing contract. Each
# entry must state why, so the list stays auditable.
STRAYS_ALLOWED = {
    # Agent-facing instructions, maintained in English only by design.
    "docs/AGENTS.md",
}


def git_blob_hash(path: Path) -> str:
    result = subprocess.run(  # nosec B603 B607  # constant argv, dev script
        ["git", "hash-object", "--", str(path)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    registries = sorted(REPO_ROOT.joinpath("docs").rglob("*.i18n.yaml"))
    if not registries:
        print("docs:i18n registry check: FAILED — no *.i18n.yaml found under docs/")
        return 1

    errors: list[str] = []
    recorded: dict[str, str] = {}
    for registry in registries:
        rel_registry = registry.relative_to(REPO_ROOT).as_posix()
        for line in registry.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = ENTRY_RE.match(line)
            if not match:
                errors.append(f"{rel_registry}: unparsable line: {line!r}")
                continue
            doc_path = match.group("path")
            if doc_path in recorded:
                errors.append(f"{rel_registry}: {doc_path} is already recorded by another registry")
            recorded[doc_path] = match.group("hash")

    for doc_path, expected in sorted(recorded.items()):
        doc = REPO_ROOT.joinpath(doc_path)
        if not doc.is_file():
            errors.append(f"ghost entry: {doc_path} is recorded but missing on disk")
            continue
        actual = git_blob_hash(doc)
        if actual != expected:
            errors.append(
                f"drift: {doc_path} is at {actual} but recorded as {expected}"
                " — update both sides and re-record with git hash-object"
            )

    actual_docs = {
        p.relative_to(REPO_ROOT).as_posix() for p in REPO_ROOT.joinpath("docs").rglob("*.md")
    }
    strays = sorted(actual_docs - set(recorded) - STRAYS_ALLOWED)
    for doc_path in strays:
        errors.append(
            f"stray: {doc_path} is not covered by any *.i18n.yaml registry"
            " — create the pairing record or add it to STRAYS_ALLOWED with a reason"
        )
    for doc_path in sorted(STRAYS_ALLOWED - actual_docs):
        errors.append(f"stale allowlist entry: {doc_path} does not exist")

    if errors:
        print(f"docs:i18n registry check: FAILED with {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(
        f"docs:i18n registry check: OK — {len(registries)} registries, "
        f"{len(recorded)} documents verified, {len(STRAYS_ALLOWED)} allowed stray(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
