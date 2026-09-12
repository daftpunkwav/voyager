"""Background memory distillation: every N user turns, condense the
recent conversation into durable memories.

Responsibilities:
- maybe_distill(): turn counter with hot-read interval (0 = off); returns a
  coroutine for the caller to schedule (Master tracks it like any background
  turn) or None when this turn is not a distillation point
- _distill_once(): render recent working-memory turns -> one LLM call asking
  for strict JSON (profile key/values + atomic facts) -> write into profile /
  semantic with source attribution; malformed output and degraded replies are
  silently skipped (a failed distillation must never surface as chat noise)

The distiller shares the metered chat LLM, so daily-token quota applies
automatically; extraction costs no extra configuration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable
from typing import Any

from agent.contracts import SettingsReader
from agent.llm import LLMClient
from agent.memory import Memory

log = logging.getLogger("agent.memory.distill")

#: How many recent working-memory entries feed one distillation
_WINDOW = 20

#: Minimum entries worth spending an LLM call on
_MIN_ENTRIES = 4

_MAX_FACTS = 5

_PROMPT = (
    "从下面的对话片段中提炼值得长期记住的信息,只输出一个 JSON 对象,不要输出其他文字:\n"
    '{"profile": {"<画像维度,如 name/preference/goal>": "<一句话>"},'
    ' "facts": [["<主体>", "<关系,如 prefers/is/works_on>", "<客体>", "<图谱节点 id,可选>"], ...]}\n'
    "要求:只提取明确、持久、可复用的信息;没有值得记的就输出空对象 {};"
    "若对话中出现过图谱节点 id(graph 工具返回的 node id),把它作为第 4 个元素关联到对应事实;"
    f"facts 最多 {_MAX_FACTS} 条;profile 最多 5 个键。"
)


def _render(entries: list[dict[str, Any]]) -> str:
    lines = [f"[{e.get('role', '?')}] {str(e.get('content', ''))[:400]}" for e in entries]
    return "\n".join(lines)


class Distiller:
    """Turn-counting trigger plus the extraction pass; no threads of its own."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        memory: Memory,
        settings: SettingsReader,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._settings = settings
        self._turns = 0

    def maybe_distill(self) -> Awaitable[None] | None:
        """Called once per user turn. Returns a distillation coroutine on
        distillation turns (caller schedules it), None otherwise."""
        try:
            interval = int(self._settings.get("agent.memory.distill_interval") or 0)
        except (TypeError, ValueError):
            return None
        if interval <= 0:
            return None
        self._turns += 1
        if self._turns % interval:
            return None
        return self._distill_once()

    async def _distill_once(self) -> None:
        entries = self._memory.working.recent(_WINDOW)
        if len(entries) < _MIN_ENTRIES:
            return
        try:
            reply = await self._llm.complete(
                [
                    {"role": "system", "content": _PROMPT},
                    {"role": "user", "content": _render(entries)},
                ]
            )
        except Exception:
            log.warning("distillation LLM call failed", exc_info=True)
            return
        if reply.degraded or not reply.text:
            return  # quota/downtime: skip silently, retry on a later turn
        parsed = _parse_json(reply.text)
        if parsed is None:
            log.info("distillation output was not valid JSON; skipped")
            return
        profile = parsed.get("profile")
        if isinstance(profile, dict):
            for key, value in list(profile.items())[:5]:
                if key and value:
                    self._memory.profile.set(str(key), str(value))
        facts = parsed.get("facts")
        if isinstance(facts, list):
            for fact in facts[:_MAX_FACTS]:
                if (
                    isinstance(fact, (list, tuple))
                    and len(fact) in (3, 4)
                    and all(str(part).strip() for part in fact[:3])
                ):
                    subject, relation, obj = (str(part).strip() for part in fact[:3])
                    # Optional 4th element: a graph node id the model saw via the
                    # graph tools; stored only, so recall can hand it back for
                    # graph__expand_neighbors without the agent importing graph
                    node_id = str(fact[3]).strip() if len(fact) == 4 else ""
                    self._memory.semantic.add(
                        subject, relation, obj, source="distill", node_id=node_id
                    )


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse the model output as a JSON object; tolerate a fenced block."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json")
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


__all__ = ["Distiller"]
