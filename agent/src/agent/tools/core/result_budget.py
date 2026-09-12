"""Tool-result budget: oversized results are truncated with the full
output spilled to a file the agent can re-read on demand.

Responsibilities:
- spill_result(): when a stringified tool result exceeds the character limit,
  keep a readable preview, write the full output under workspace/spill/, and
  append the file path so the model can pull the rest via read_file
- bound_spill_dir(): FIFO cleanup so the spill directory stays bounded

The spill file deliberately lives inside the workspace jail: no extra read
root is needed, and the agent's existing fs policy applies unchanged.
"""

from __future__ import annotations

import time
from pathlib import Path

#: Preview length kept in the tool message when a result is spilled
PREVIEW_KEEP = 2000

#: FIFO cap on spill files: the oldest are deleted on write beyond this count
MAX_SPILL_FILES = 200


def _safe_name(tool: str) -> str:
    """Tool name -> filename-safe fragment (bridge names contain __)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in tool) or "tool"


def spill_result(
    result: str,
    *,
    tool: str,
    spill_dir: Path,
    limit: int,
    preview: int = PREVIEW_KEEP,
) -> str:
    """Return `result` unchanged when within `limit`; otherwise truncate to a
    preview with the full output spilled to a file.

    Self-checking by design: callers may pass any result without pre-checking
    the limit (0 or negative = unlimited).
    """
    if limit <= 0 or len(result) <= limit:
        return result
    spill_dir.mkdir(parents=True, exist_ok=True)
    path = spill_dir / f"{_safe_name(tool)}-{time.time_ns()}.txt"
    path.write_text(result, encoding="utf-8")
    head = result[:preview]
    return (
        f"{head}\n…[输出超长已截断,完整输出({len(result)} 字符)已保存到 "
        f"{path},可用 read_file 分段查看]"
    )


def bound_spill_dir(spill_dir: Path, *, cap: int = MAX_SPILL_FILES) -> int:
    """Delete the oldest spill files beyond `cap`; returns the removed count.

    Missing directory is a no-op; individual failures (concurrent cleanup,
    read-only file) are skipped without failing the write path.
    """
    if not spill_dir.is_dir():
        return 0
    files = sorted(
        (p for p in spill_dir.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
    )
    removed = 0
    for path in files[: max(len(files) - cap, 0)]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


__all__ = ["MAX_SPILL_FILES", "PREVIEW_KEEP", "bound_spill_dir", "spill_result"]
