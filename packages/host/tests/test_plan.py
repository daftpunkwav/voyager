"""Unit tests for assembly planning: enablement, topology, settings
whitelist. No domain is imported.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from host.plan import select_enabled, topo_order
from host.scan import ServiceCard


def _card(domain: str, **overrides) -> ServiceCard:
    kwargs: dict[str, Any] = {
        "domain": domain,
        "module": f"svc.{domain}",
        "name": domain,
        "version": "0.1.0",
        "protocol": "0.1.0",
        "port": 1,
    }
    kwargs.update(overrides)
    return ServiceCard(**kwargs)


def test_select_enabled_uses_card_flag_and_skips_gateway() -> None:
    cards = [
        _card("alpha"),
        _card("beta", enabled_by_default=False),
        _card("shell", role="gateway"),
    ]
    assert [c.domain for c in select_enabled(cards, env_raw="")] == ["alpha"]


def test_select_enabled_env_whitelist_wins(monkeypatch) -> None:
    cards = [
        _card("alpha"),
        _card("beta", enabled_by_default=False),
    ]
    monkeypatch.setenv("ENABLE_DOMAINS", "beta")
    assert [c.domain for c in select_enabled(cards)] == ["beta"]


def test_select_enabled_setting_names_when_env_empty() -> None:
    cards = [
        _card("alpha"),
        _card("beta", enabled_by_default=False),
    ]
    got = select_enabled(cards, env_raw="", enabled_names=["beta"])
    assert [c.domain for c in got] == ["beta"]


def test_select_enabled_env_beats_setting_names() -> None:
    cards = [_card("alpha"), _card("beta")]
    got = select_enabled(cards, env_raw="alpha", enabled_names=["beta"])
    assert [c.domain for c in got] == ["alpha"]


def test_topo_order_dependency_first() -> None:
    alpha = _card("alpha")
    beta = _card("beta", depends_on=("alpha",))
    # Input deliberately reverse of dependency order
    assert [c.domain for c in topo_order([beta, alpha])] == ["alpha", "beta"]


def test_topo_order_cycle_raises() -> None:
    a = _card("a", depends_on=("b",))
    b = _card("b", depends_on=("a",))
    with pytest.raises(RuntimeError, match="cycle"):
        topo_order([a, b])


def test_topo_order_missing_dep_warned(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        ordered = topo_order([_card("solo", depends_on=("ghost",))])
    assert [c.domain for c in ordered] == ["solo"]
    assert any("ghost" in r.getMessage() for r in caplog.records)
