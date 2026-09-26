"""Naming-neutrality scan: production source must not contain brand literals
(the single brand source is the root brand.json).

Scan surface: backend domain .py files plus frontend apps/web/src .ts/.tsx. Quoted
string constants are also joined and re-checked so split-character escapes cannot dodge
the line-by-line grep.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BRAND_RE = re.compile(r"voyager|repopilot", re.IGNORECASE)
QUOTED_RE = re.compile(r"""['"]([^'"\n]{1,64})['"]""")

_PY_DOMAINS = ("agent", "packages")
_WEB_SRC = ROOT / "apps" / "web" / "src"


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for domain in _PY_DOMAINS:
        for path in (ROOT / domain).rglob("*.py"):
            if "tests" in path.parts or "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            files.append(path)
    if _WEB_SRC.exists():
        files.extend(_WEB_SRC.rglob("*.ts"))
        files.extend(_WEB_SRC.rglob("*.tsx"))
    return files


def _scan() -> list[str]:
    hits: list[str] = []
    for path in _iter_source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BRAND_RE.search(line):
                hits.append(f"{rel}:{lineno}:{line.strip()[:120]}")
        # Split-character escape detection: quoted constants joined together hitting a brand word is also a violation
        joined = "".join(QUOTED_RE.findall(text))
        match = BRAND_RE.search(joined)
        if match:
            ctx = joined[max(0, match.start() - 12) : match.end() + 12]
            hits.append(f"{rel}:拼接字符串:引号常量连读命中品牌词「…{ctx}…」")
    return hits


def test_no_brand_literal_in_production_source() -> None:
    hits = _scan()
    if hits:
        raise AssertionError("生产源码出现品牌字面量:\n" + "\n".join(hits))


def test_scanner_catches_deliberate_dirty_string() -> None:
    """Dirty content must be caught: both the line-by-line and the split-character-join channels have to hit."""
    assert BRAND_RE.search("# old name was Voyager-Agent, do not use")
    split_chars = "['R', 'e', 'p', 'o', 'P', 'i', 'l', 'o', 't'].join('')"
    assert BRAND_RE.search("".join(QUOTED_RE.findall(split_chars)))
