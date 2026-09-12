"""grep tool: jailed regex content search (returns file:line: text).

Read-only companion to read_file: finds where a pattern lives so the agent
stops paging whole trees. Walk hits bypass resolve(), so containment is
re-checked per file (a workspace symlink must not launder reads).
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail

#: Per-file read cap for grep: a generated dump must not be loaded fully.
_MAX_FILE_BYTES = 1_000_000

#: Default and hard caps on reported matches (totals are still counted).
_DEFAULT_MAX_MATCHES = 50
_HARD_MAX_MATCHES = 200

#: Output budget for one grep result (characters); beyond it the tail is cut
#: with a narrowing hint.
_MAX_OUTPUT_CHARS = 8000

#: Max line length kept per match (characters); longer lines are cut.
_MAX_LINE_CHARS = 300


def _is_binary(head: bytes) -> bool:
    """Null-byte heuristic on the file head; decoding happens with
    errors="replace" afterwards, so this only skips real binaries."""
    return b"\x00" in head


def _iter_files(target: Path, include: str) -> Any:
    if target.is_file():
        yield target
        return
    for dirpath, _dirnames, filenames in os.walk(target, followlinks=False):
        for name in filenames:
            if fnmatch.fnmatchcase(name, include):
                yield Path(dirpath) / name


def grep_tool(jail: Jail) -> AgentTool:
    def grep(
        pattern: str, path: str = ".", include: str = "*", max_matches: int = _DEFAULT_MAX_MATCHES
    ) -> str:
        if not (pattern or "").strip():
            return "[参数错误] pattern 不能为空"
        try:
            matcher = re.compile(pattern)
        except re.error as exc:
            return f"[参数错误] 正则无效: {exc}"
        target = jail.resolve(path, allow_read_roots=True, allow_write_roots=True)
        if not target.exists():
            return f"[失败] 路径不存在: {jail.display(target)}"
        hits: list[str] = []
        shown = 0
        try:
            show = max(1, min(int(max_matches), _HARD_MAX_MATCHES))
        except (TypeError, ValueError):
            return "[参数错误] max_matches 需要整数"
        probe = show + 1  # one extra decides honestly whether more exist
        total = 0
        files = 0
        skipped = 0
        for candidate in _iter_files(target, include or "*"):
            if total >= probe:
                break
            # Walk hits bypass resolve(): re-check containment so a workspace
            # symlink pointing outside cannot launder reads (read_file on the
            # same path refuses via resolve).
            if not jail.contains(candidate.resolve()):
                skipped += 1
                continue
            try:
                if candidate.stat().st_size > _MAX_FILE_BYTES:
                    skipped += 1
                    continue
                head = candidate.read_bytes()[:8192]
            except OSError:
                skipped += 1
                continue
            if _is_binary(head):
                skipped += 1
                continue
            files += 1
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                skipped += 1
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if total >= probe:
                    break
                if matcher.search(line):
                    total += 1
                    if shown < show:
                        shown += 1
                        clipped = line.strip()
                        if len(clipped) > _MAX_LINE_CHARS:
                            clipped = clipped[:_MAX_LINE_CHARS] + "…"
                        hits.append(f"{jail.display(candidate)}:{lineno}: {clipped}")
        if not hits:
            return f"[无匹配] {pattern} 在 {jail.display(target)} 下没有命中"
        scope = f"已扫 {files} 个文件" + (
            f"，跳过 {skipped} 个(二进制/超大/越界)" if skipped else ""
        )
        if total > show:
            head_note = f"[命中 {show}+ 处，仅显示前 {show} 条，{scope}]"
        else:
            head_note = f"[命中 {total} 处，{scope}]"
        out = head_note + "\n" + "\n".join(hits)
        if len(out) > _MAX_OUTPUT_CHARS:
            out = out[:_MAX_OUTPUT_CHARS] + "\n…[截断] 用更具体的 pattern / include 缩小范围"
        return out

    return AgentTool(
        name="grep",
        description="在工作目录内按正则搜文件内容(返回 文件:行号: 文本)",
        handler=grep,
        dimension="fs",
        concurrent_safe=True,  # read-only: safe to batch in parallel
        schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "include": {"type": "string"},
                "max_matches": {"type": "integer"},
            },
            "required": ["pattern"],
        },
    )


__all__ = ["grep_tool"]
