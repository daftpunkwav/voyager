"""Bridge tests: registry -> AgentTool naming, metadata, guard-chain
invocation, and trace propagation.
"""

import asyncio

from agent.runtime.trace import reset_current_trace, set_current_trace
from gateway.mounts import MountSpec
from host.bridge import make_domain_tools
from platform_capability import Registry, SqliteAuditSink, capability


def _echo_mounts():
    reg = Registry("echo")

    @capability(reg, name="ping", description="echo test", cost=2, reversible=False)
    async def ping(text: str = "") -> dict:
        return {"pong": text}

    return [MountSpec(domain="echo", registry=reg, probe=None)]


def test_names_and_metadata() -> None:
    tools = make_domain_tools(_echo_mounts())
    assert list(tools) == ["echo__ping"]
    tool = tools["echo__ping"]
    assert tool.name == "echo__ping"
    assert tool.description == "[echo] echo test"
    assert tool.dimension == "app"  # domain capabilities all use the app dimension
    assert tool.write is True  # write defaults to True when not declared explicitly
    assert tool.irreversible is True  # reversible=False passed through


def test_unmodeled_capability_gets_signature_schema() -> None:
    """An unmodeled capability used to expose an empty schema, leaving the LLM
    to guess argument names (agent-side TypeError loops on create_note)."""
    tools = make_domain_tools(_echo_mounts())
    schema = tools["echo__ping"].schema
    assert schema["properties"]["text"] == {"type": "string", "default": ""}
    assert schema["required"] == []


def test_declared_dimension_passes_through() -> None:
    """A capability may declare its policy dimension (save_url fetches URLs
    and bridges as "network" so the agent-facing fetch obeys the same
    allowlist as the native web tools); undeclared ones stay "app"."""

    reg = Registry("net")

    @capability(
        reg,
        name="save_url",
        description="fetch a page",
        dimension="network",
    )
    async def save_url(url: str = "") -> dict:
        return {"url": url}

    tools = make_domain_tools([MountSpec(domain="net", registry=reg, probe=None)])
    assert tools["net__save_url"].dimension == "network"


def test_write_is_explicit_not_cost_derived() -> None:
    """write is decoupled from cost: explicit declarations pass through as-is,
    and derivation from cost is not allowed."""
    reg = Registry("w")

    @capability(
        reg, name="read_only", description="zero cost but declared write", cost=0, write=True
    )
    async def read_only() -> dict:
        return {}

    @capability(
        reg, name="expensive_read", description="high cost but read-only", cost=5, write=False
    )
    async def expensive_read() -> dict:
        return {}

    tools = make_domain_tools([MountSpec(domain="w", registry=reg, probe=None)])
    assert tools["w__read_only"].write is True  # cost=0, write=True
    assert tools["w__expensive_read"].write is False  # cost=5, write=False


def test_handler_calls_through_capability_framework() -> None:
    tools = make_domain_tools(_echo_mounts())
    out = asyncio.run(tools["echo__ping"].handler(text="hi"))
    assert out == {"pong": "hi"}


def test_multiple_mounts_no_name_collision() -> None:
    reg_a = Registry("a")
    reg_b = Registry("b")
    capability(reg_a, name="same", description="a")(lambda: {"from": "a"})
    capability(reg_b, name="same", description="b")(lambda: {"from": "b"})
    tools = make_domain_tools(
        [
            MountSpec(domain="a", registry=reg_a, probe=None),
            MountSpec(domain="b", registry=reg_b, probe=None),
        ]
    )
    assert set(tools) == {"a__same", "b__same"}
    assert asyncio.run(tools["a__same"].handler()) == {"from": "a"}
    assert asyncio.run(tools["b__same"].handler()) == {"from": "b"}


def test_handler_carries_current_trace(tmp_path) -> None:
    """When a trace is active on the chain, the agent's capability call reuses it
    so the audit trail replays end to end."""
    sink = SqliteAuditSink(tmp_path / "audit.db")
    tools = make_domain_tools(_echo_mounts(), audit=[sink])
    token = set_current_trace("trace-from-user-message")
    try:
        out = asyncio.run(tools["echo__ping"].handler(text="hi"))
        assert out == {"pong": "hi"}
    finally:
        reset_current_trace(token)
    rows = sink.recent(trace_id="trace-from-user-message")
    assert len(rows) == 1 and rows[0]["capability"] == "ping"
    sink.close()
