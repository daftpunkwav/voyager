"""Card-driven assembly end to end: a mock domain dropped into a
temporary domain root appears in the agent tool roster without touching
agent/ source (the "capabilities are discovered automatically" acceptance
criterion), plus topological wire order, late-bound cross-domain calls, the
ENABLE_DOMAINS whitelist override, and fail-fast contract violations.

Each test uses a unique domain name: importlib caches modules by name, so
reused names would leak state between tests.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import pytest
from host.assemble import build
from host.bridge import agent_context
from platform_capability import execute

_WIRING = '''"""Mock domain wiring (test fixture): registry plus late-bound call echo."""

from dataclasses import dataclass

from platform_capability import Registry, Wiring, capability

registry = Registry("{domain}")

_call_sync = None


def init_deps(call_sync=None):
    global _call_sync
    _call_sync = call_sync


@dataclass
class EchoIn:
    text: str = ""


@capability(registry, name="echo", description="echo text back",
            input_model=EchoIn)
def echo(data: EchoIn) -> dict:
    return {{"echo": data.text, "domain": "{domain}"}}


@capability(registry, name="ping_neighbor", description="call alpha via call_sync")
def ping_neighbor() -> dict:
    assert _call_sync is not None, "call_sync was not injected"
    return _call_sync("{dep}", "echo", {{"text": "ping"}})


def wire(data_dir, *, call_sync=None):
    init_deps(call_sync)
    return Wiring(registry=registry, probe=lambda: {{"status": "up"}})
'''


class MockDomain:
    """A throwaway domain package under a temporary namespace root."""

    def __init__(self, root: Path, name: str, *, card: dict, wiring: str):
        self.name = name
        pkg = root / name
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "service.json").write_text(json.dumps(card), encoding="utf-8")
        (pkg / "wiring.py").write_text(wiring, encoding="utf-8")


def _card(name: str, **overrides) -> dict:
    base = {
        "name": name,
        "version": "0.1.0",
        "protocol": "0.1.0",
        "capabilities": ["echo", "ping_neighbor"],
        "subscribes": [],
        "publishes": [],
        "status": "implemented",
    }
    base.update(overrides)
    return base


def _fresh_name() -> str:
    return "mock" + uuid.uuid4().hex[:8]


@pytest.fixture()
def domain_root(tmp_path, monkeypatch):
    root = tmp_path / "domainroot"
    root.mkdir()
    monkeypatch.syspath_prepend(str(root))
    yield root


def _build(tmp_path, domain_root: Path, prefix: str = ""):
    return build(
        tmp_path / "data", tmp_path / "ws", domains_root=domain_root, domains_prefix=prefix
    )


def test_mock_domain_reaches_agent_without_agent_changes(tmp_path, domain_root) -> None:
    alpha = _fresh_name()
    MockDomain(
        domain_root, alpha, card=_card(alpha), wiring=_WIRING.format(domain=alpha, dep=alpha)
    )
    app = _build(tmp_path, domain_root)
    names = app.state.backend.agent.spawner._toolbelt.names()
    assert f"{alpha}__echo" in names
    assert f"{alpha}__ping_neighbor" in names


def test_topology_order_and_late_bound_call(tmp_path, domain_root) -> None:
    alpha = _fresh_name()
    beta = _fresh_name()
    MockDomain(
        domain_root, alpha, card=_card(alpha), wiring=_WIRING.format(domain=alpha, dep=alpha)
    )
    MockDomain(
        domain_root,
        beta,
        card=_card(beta, needs=["call_sync"], depends_on=[alpha]),
        wiring=_WIRING.format(domain=beta, dep=alpha),
    )
    app = _build(tmp_path, domain_root)
    backend = app.state.backend
    # depends_on drives wire/start order: the dependency is assembled first
    assert list(backend.wirings) == [alpha, beta]
    # late-bound cross-domain call rides the capability guard chain end to end
    result = asyncio.run(
        execute(backend.wirings[beta].registry, "ping_neighbor", agent_context(), {})
    )
    assert result["echo"] == "ping"
    assert result["domain"] == alpha


def test_disabled_domain_stays_unwired_and_env_whitelist_overrides(
    tmp_path, domain_root, monkeypatch
) -> None:
    gamma = _fresh_name()
    MockDomain(
        domain_root,
        gamma,
        card=_card(gamma, enabled_by_default=False),
        wiring=_WIRING.format(domain=gamma, dep=gamma),
    )
    app = _build(tmp_path, domain_root)
    assert gamma not in app.state.backend.wirings
    assert f"{gamma}__echo" not in app.state.backend.agent.spawner._toolbelt.names()

    monkeypatch.setenv("ENABLE_DOMAINS", gamma)
    app2 = _build(tmp_path, domain_root)
    assert gamma in app2.state.backend.wirings


def test_unknown_needs_key_fails_startup(tmp_path, domain_root) -> None:
    name = _fresh_name()
    MockDomain(
        domain_root,
        name,
        card=_card(name, needs=["no_such_facility"]),
        wiring=_WIRING.format(domain=name, dep=name),
    )
    with pytest.raises(RuntimeError, match="unknown key"):
        _build(tmp_path, domain_root)


def test_wire_extras_rejected_when_wire_has_no_such_param(tmp_path, domain_root) -> None:
    name = _fresh_name()
    MockDomain(domain_root, name, card=_card(name), wiring=_WIRING.format(domain=name, dep=name))
    with pytest.raises(RuntimeError, match="does not accept"):
        build(
            tmp_path / "data",
            tmp_path / "ws",
            domains_root=domain_root,
            domains_prefix="",
            wire_extras={name: {"no_such_hook": 1}},
        )


def test_wire_extras_unknown_domain_fails_startup(tmp_path, domain_root) -> None:
    name = _fresh_name()
    MockDomain(domain_root, name, card=_card(name), wiring=_WIRING.format(domain=name, dep=name))
    with pytest.raises(RuntimeError, match="unwired domains"):
        build(
            tmp_path / "data",
            tmp_path / "ws",
            domains_root=domain_root,
            domains_prefix="",
            wire_extras={"ghost": {"x": 1}},
        )


def test_dependency_cycle_fails_startup(tmp_path, domain_root) -> None:
    a = _fresh_name()
    b = _fresh_name()
    MockDomain(
        domain_root, a, card=_card(a, depends_on=[b]), wiring=_WIRING.format(domain=a, dep=a)
    )
    MockDomain(
        domain_root, b, card=_card(b, depends_on=[a]), wiring=_WIRING.format(domain=b, dep=b)
    )
    with pytest.raises(RuntimeError, match="cycle"):
        _build(tmp_path, domain_root)


def test_missing_dependency_is_ignored_with_warning(tmp_path, domain_root, caplog) -> None:
    import logging

    name = _fresh_name()
    MockDomain(
        domain_root,
        name,
        card=_card(name, depends_on=["ghost"]),
        wiring=_WIRING.format(domain=name, dep=name),
    )
    with caplog.at_level(logging.WARNING):
        app = _build(tmp_path, domain_root)
    assert name in app.state.backend.wirings
