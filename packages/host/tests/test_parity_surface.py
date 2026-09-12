"""Parity freeze: every capability the human REST projection mounts is
reachable by the agent as a same-named tool, except the frozen exceptions.

Domains: <domain>__<capability> (host bridge). Agent registry: <name>
(tools/<group>/<name>.py). The exception tables live in agent.parity with a
reason per entry; this test fails when a capability appears on one side
only and is not listed, or when a listed exception stops being one.
"""

from __future__ import annotations

from agent.parity import AGENT_ONLY_TOOLS, HUMAN_ONLY_CAPABILITIES
from host.assemble import build


def _backend(tmp_path):
    app = build(tmp_path / "data", tmp_path / "ws")
    return app.state.backend


class TestDomainParity:
    def test_every_mounted_domain_capability_has_a_bridge_tool(self, tmp_path) -> None:
        backend = _backend(tmp_path)
        try:
            tools = set(backend.agent.spawner._toolbelt.names())
            missing = []
            for domain, wiring in backend.wirings.items():
                for cap in wiring.registry.all():
                    if f"{domain}__{cap.name}" not in tools:
                        missing.append(f"{domain}__{cap.name}")
            assert missing == [], f"domain capabilities without an agent tool: {missing}"
        finally:
            backend.agent.close()


class TestAgentRegistryParity:
    def test_every_agent_capability_has_a_same_named_tool_or_a_reason(self, tmp_path) -> None:
        backend = _backend(tmp_path)
        try:
            tools = set(backend.agent.spawner._toolbelt.names())
            caps = set(backend.agent.registry.names())
            unexplained = sorted(caps - tools - set(HUMAN_ONLY_CAPABILITIES))
            assert unexplained == [], (
                f"capabilities without a tool and without a reason: {unexplained}"
            )
            stale = sorted(name for name in HUMAN_ONLY_CAPABILITIES if name in tools)
            assert stale == [], f"listed as human-only but a tool exists: {stale}"
            unknown = sorted(name for name in HUMAN_ONLY_CAPABILITIES if name not in caps)
            assert unknown == [], f"exception names no longer registered: {unknown}"
        finally:
            backend.agent.close()

    def test_every_agent_only_tool_is_declared(self, tmp_path) -> None:
        backend = _backend(tmp_path)
        try:
            belt = backend.agent.spawner._toolbelt
            builtin = {n for n in belt.names() if "__" not in n}
            caps = set(backend.agent.registry.names())
            unexplained = sorted(builtin - caps - set(AGENT_ONLY_TOOLS))
            assert unexplained == [], (
                f"agent tools without a capability and without a reason: {unexplained}"
            )
            stale = sorted(name for name in AGENT_ONLY_TOOLS if name in caps)
            assert stale == [], f"listed as agent-only but a capability exists: {stale}"
        finally:
            backend.agent.close()

    def test_exception_reasons_are_non_empty(self) -> None:
        for table in (HUMAN_ONLY_CAPABILITIES, AGENT_ONLY_TOOLS):
            for name, reason in table.items():
                assert reason.strip(), f"{name}: exception without a reason"
