"""Check internal links and pair reciprocity across the docs/ tree.

Deterministic and local-only by design, so it can gate merges:

- Relative markdown link targets must exist on disk. HTTP(S), mailto
  and same-page anchors are skipped — the network is never consulted.
- Links inside fenced code blocks and inline code spans are ignored:
  the pairing-contract pages teach the link syntax with `foo.md`
  examples, which are not real targets.
- Every registered bilingual pair must reciprocate near the top: the
  English side links its `.zh.md` twin and vice versa (pairing
  contract, docs/i18n/README.md).
"""

from __future__ import annotations

import re
import sys
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def strip_inline_code(line: str) -> str:
    """Blank inline code spans so their content is never scanned."""
    segments = line.split("`")
    return "".join(seg if i % 2 == 0 else "\0" * len(seg) for i, seg in enumerate(segments))


def main() -> int:
    docs = REPO_ROOT.joinpath("docs")
    files = sorted(docs.rglob("*.md"))
    errors: list[str] = []

    for md in files:
        rel = md.relative_to(REPO_ROOT).as_posix()
        fenced = False
        for lineno, raw in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE_RE.match(raw):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in LINK_RE.finditer(strip_inline_code(raw)):
                target = match.group(1)
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                path_part = urllib.parse.unquote(target.split("#", 1)[0])
                if not path_part:
                    continue  # pure same-page anchor
                resolved = (md.parent / path_part).resolve()
                if not resolved.exists():
                    errors.append(f"{rel}:{lineno}: broken link -> {target}")

        # Pair reciprocity: both sides must surface the twin link near the
        # top (immediately after the H1 per the contract; six lines is
        # generous without allowing it to drift into the body).
        name = md.name
        if name == "AGENTS.md":
            continue  # working conventions, not a document — unpaired
        twin = name[:-3] + ".zh.md" if not name.endswith(".zh.md") else name[:-6] + ".md"
        if not (md.parent / twin).exists():
            continue
        head = "\n".join(md.read_text(encoding="utf-8").splitlines()[:6])
        if twin not in head:
            errors.append(f"{rel}: no reciprocal link to {twin} within the first 6 lines")

    if errors:
        print(f"docs:link check: FAILED with {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"docs:link check: OK — {len(files)} documents, internal links and pairs intact")
    return 0


if __name__ == "__main__":
    sys.exit(main())
