"""reach_out: anti-bombing budget gate and visible (L1) dimension — a
prompt-injected send loop hits the same caps as the proactive engine and is
never silently delivered."""

from __future__ import annotations

from types import SimpleNamespace

from agent.tools.interact.reach_out import reach_out_tool


class _Budget:
    def __init__(self, allow: bool) -> None:
        self.allow_value = allow
        self.recorded: list[str] = []
        self.checked: list[str] = []

    def allow(self, *, session: str):
        self.checked.append(session)
        return SimpleNamespace(
            allow=self.allow_value, reason="session cap reached" if not self.allow_value else ""
        )

    def record(self, *, session: str) -> None:
        self.recorded.append(session)


def _sink():
    sent: list[tuple[str, str]] = []

    async def reply(text: str, session: str = "") -> None:
        sent.append((text, session))

    return sent, reply


async def test_budget_refusal_blocks_send() -> None:
    sent, reply = _sink()
    budget = _Budget(allow=False)
    tool = reach_out_tool(reply, budget=budget)
    out = await tool.handler(session_id="s1", text="hello")
    assert sent == []  # nothing delivered
    assert "已拦截" in str(out) and "session cap reached" in str(out)
    assert budget.checked == ["s1"]


async def test_allowed_send_records_budget() -> None:
    sent, reply = _sink()
    budget = _Budget(allow=True)
    tool = reach_out_tool(reply, budget=budget)
    out = await tool.handler(session_id="s1", text="hello")
    assert sent == [("hello", "s1")]
    assert out == {"sent": True, "session": "s1"}
    assert budget.recorded == ["s1"]


async def test_dimension_is_visible_app_not_none() -> None:
    """write=True on dimension "none" resolved to L0 (silent); "app" makes the
    send surface as an L1 notification."""
    _, reply = _sink()
    tool = reach_out_tool(reply)
    assert tool.dimension == "app"
    assert tool.write is True
