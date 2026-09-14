"""Tool-result budget: oversized results are truncated with the full
output spilled to a file the agent can re-read on demand.

Responsibilities:
- spill_result(): when a stringified tool result exceeds the character and/or
  line budget, keep a readable preview, write the full output under
  workspace/spill/, and append the file path so the model can pull the rest
  via read_file
- bound_spill_dir(): FIFO + age cleanup so the spill directory stays bounded

The spill file deliberately lives inside the workspace jail: no extra read
root is needed, and the agent's existing fs policy applies unchanged.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

#: Preview length kept in the tool message when a result is spilled
PREVIEW_KEEP = 2000

#: FIFO cap on spill files: the oldest are deleted on write beyond this count
MAX_SPILL_FILES = 200

#: Default age bound on spill files: older files are removed on write
MAX_AGE_SECONDS = 7 * 24 * 3600


def _safe_name(tool: str) -> str:
    """Tool name -> filename-safe fragment (bridge names contain __)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in tool) or "tool"


def spill_result(
    result: str,
    *,
    tool: str,
    spill_dir: Path,
    limit: int,
    max_lines: int = 0,
    preview: int = PREVIEW_KEEP,
) -> str:
    """Return `result` unchanged when within budget; otherwise truncate to a
    preview with the full output spilled to a file.

    Budget is dual-dimension (either hits): `limit` characters and, when
    `max_lines` > 0, that many lines. Self-checking by design: callers may
    pass any result without pre-checking (0 or negative = dimension off).
    """
    over_chars = limit > 0 and len(result) > limit
    over_lines = max_lines > 0 and result.count("\n") + 1 > max_lines
    if not (over_chars or over_lines):
        return result
    spill_dir.mkdir(parents=True, exist_ok=True)
    # time_ns keeps names sortable; the uuid fragment guards against Windows
    # clock granularity, where two spills in the same tick would otherwise
    # collide and the first spill file would be silently overwritten
    path = spill_dir / f"{_safe_name(tool)}-{time.time_ns()}-{uuid.uuid4().hex[:6]}.txt"
    path.write_text(result, encoding="utf-8")
    head = result[:preview]
    return (
        f"{head}\n…[输出超长已截断,完整输出({len(result)} 字符)已保存到 "
        f"{path},可用 read_file 分段查看]"
    )


def bound_spill_dir(
    spill_dir: Path, *, cap: int = MAX_SPILL_FILES, max_age_s: float | None = None
) -> int:
    """Delete spill files beyond `cap` (oldest first) and, when `max_age_s`
    is set, files whose last modification predates it; returns the removed
    count. Missing directory is a no-op; individual failures (concurrent
    cleanup, read-only file) are skipped without failing the write path."""
    if not spill_dir.is_dir():
        return 0
    now = time.time()
    files = sorted(
        ((p, p.stat()) for p in spill_dir.iterdir() if p.is_file()),
        key=lambda t: t[1].st_mtime,
    )
    removed = 0
    for index, (path, stat) in enumerate(files):
        over_cap = index < len(files) - cap if cap > 0 else True
        over_age = max_age_s is not None and now - stat.st_mtime > max_age_s
        if not (over_cap or over_age):
            break  # sorted by mtime: once one file is in bounds, the rest are
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


__all__ = ["MAX_AGE_SECONDS", "MAX_SPILL_FILES", "PREVIEW_KEEP", "bound_spill_dir", "spill_result"]
