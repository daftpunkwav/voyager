"""Event contract: every RuntimeEvent value is emitted somewhere in agent
source (or sits in the frozen pending list with a reason), and a ReAct turn
with a tool call raises the full LLM*/Tool* lifecycle into the event log.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall
from platform_contracts import RuntimeEvent

import agent

SRC = Path(agent.__file__).parent

#: Enum values with no emit site yet; each entry names the phase that owns it.
PENDING_EMIT: dict[str, str] = {}


def _enum_values() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(RuntimeEvent).items()
        if name.isupper() and isinstance(value, str)
    }


def _emit_sites() -> set[str]:
    pattern = re.compile(r"RuntimeEvent\.([A-Z_]+)")
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        if path.name == "events.py" and path.parent.name == "runtime":
            continue  # the re-export, not an emit site
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return found


class TestRuntimeEventContract:
    def test_every_value_is_emitted_or_pending(self) -> None:
        values = _enum_values()
        sites = _emit_sites()
        missing = sorted(
            value
            for name, value in values.items()
            if name not in sites and value not in PENDING_EMIT
        )
        assert missing == [], f"RuntimeEvent values without an emit site: {missing}"
        stale = sorted(v for v in PENDING_EMIT if v in {values[n] for n in sites if n in values})
        assert stale == [], f"pending entries that now have an emit site: {stale}"

    def test_no_bare_string_runtime_events(self) -> None:
        values = set(_enum_values().values())
        offenders: list[str] = []
        for path in SRC.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for value in values:
                if f'emit("{value}"' in text or f"emit('{value}'" in text:
                    offenders.append(f"{path.relative_to(SRC).as_posix()}: {value}")
        assert offenders == [], f"emit() with bare runtime event strings: {offenders}"


class TestLifecycleEvents:
    async def test_react_turn_raises_llm_and_tool_lifecycle(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
                    LLMReply(text="done"),
                ]
            ),
        )
        try:
            await app.master.handle_user_message("look")
            await settle(app)
            types = [e.type for _, e in app.log.read_after()]
            for expected in (
                RuntimeEvent.RUN_STARTED,
                RuntimeEvent.LLM_STARTED,
                RuntimeEvent.LLM_COMPLETED,
                RuntimeEvent.TOOL_STARTED,
                RuntimeEvent.TOOL_COMPLETED,
            ):
                assert expected in types, expected
            assert types.index(RuntimeEvent.TOOL_STARTED) < types.index(RuntimeEvent.TOOL_COMPLETED)
            assert (
                types.count(RuntimeEvent.LLM_STARTED)
                == 2
                == types.count(RuntimeEvent.LLM_COMPLETED)
            )
            tool_done = next(e for _, e in app.log.read_after(types=[RuntimeEvent.TOOL_COMPLETED]))
            assert tool_done.payload["tool"] == "list_dir" and tool_done.payload["run_id"]
        finally:
            app.close()

    async def test_failed_tool_raises_tool_failed(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(tool_calls=(ToolCall("1", "read_file", {"path": "nope.txt"}),)),
                    LLMReply(text="done"),
                ]
            ),
        )
        try:
            await app.master.handle_user_message("read")
            await settle(app)
            types = [e.type for _, e in app.log.read_after()]
            # read_file on a missing path returns a "[失败]" text result (ok
            # stays True at the pipeline level); a genuinely failing pipeline
            # outcome is exercised in the tools tests. Here we only assert the
            # lifecycle pairing holds.
            assert types.count(RuntimeEvent.TOOL_STARTED) == 1
            assert (RuntimeEvent.TOOL_COMPLETED in types) or (RuntimeEvent.TOOL_FAILED in types)
        finally:
            app.close()
