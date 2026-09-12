"""Unit tests for host.scan: card parsing, normalization
and skip rules.

Discovery must never fail startup: any broken or missing card is skipped;
valid cards come out sorted and normalized. Reserved composition directories
(platform / host) are never domains.
"""

import json
import logging
from pathlib import Path

import pytest
from host.scan import scan


def _write_card(root: Path, domain: str, card: dict | str | None) -> Path:
    child = root / domain
    child.mkdir(parents=True)
    if card is None:
        pass  # no service.json at all
    elif isinstance(card, str):
        (child / "service.json").write_text(card, encoding="utf-8")
    else:
        (child / "service.json").write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    return child


def _card(**overrides) -> dict:
    base = {
        "name": "demo",
        "version": "0.1.0",
        "protocol": "0.1.0",
        "port": 8100,
        "capabilities": ["echo"],
        "subscribes": [],
        "publishes": [],
        "status": "implemented",
    }
    base.update(overrides)
    return base


def test_scan_normalizes_and_sorts_by_directory(tmp_path) -> None:
    _write_card(tmp_path, "zeta", _card(name="zeta-dom"))
    _write_card(
        tmp_path,
        "alpha",
        _card(name="alpha-dom", needs=["bus"], enabled_by_default=False, depends_on=["zeta"]),
    )
    cards = scan(tmp_path, "svc")
    assert [c.domain for c in cards] == ["alpha", "zeta"]
    first = cards[0]
    assert first.module == "svc.alpha"
    assert first.name == "alpha-dom"
    assert first.enabled_by_default is False
    assert first.needs == ("bus",)
    assert first.depends_on == ("zeta",)
    assert first.role == "domain"
    assert first.capabilities == ("echo",)
    assert first.port == 8100


def test_scan_skips_underscore_dirs_and_missing_cards(tmp_path, caplog) -> None:
    _write_card(tmp_path, "_template", _card())
    _write_card(tmp_path, "plain", None)  # directory without a card
    _write_card(tmp_path, "real", _card())
    with caplog.at_level(logging.DEBUG):
        cards = scan(tmp_path, "svc")
    assert [c.domain for c in cards] == ["real"]


def test_scan_skips_broken_cards_without_raising(tmp_path, caplog) -> None:
    _write_card(tmp_path, "bad_json", "{not json")
    _write_card(tmp_path, "not_object", "[1, 2]")
    _write_card(tmp_path, "missing_version", {"name": "x"})
    _write_card(tmp_path, "bad_needs", _card(needs="bus"))  # not a list
    _write_card(tmp_path, "bad_needs_item", _card(needs=["bus", 3]))
    _write_card(tmp_path, "bad_enabled", _card(enabled_by_default="yes"))
    _write_card(tmp_path, "bad_role", _card(role="worker"))
    _write_card(tmp_path, "bad_port", _card(port="8100"))
    with caplog.at_level(logging.WARNING):
        cards = scan(tmp_path, "svc")
    assert cards == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 8


def test_scan_accepts_gateway_role(tmp_path) -> None:
    _write_card(tmp_path, "shell", _card(role="gateway"))
    cards = scan(tmp_path, "svc")
    assert [c.domain for c in cards] == ["shell"]
    assert cards[0].role == "gateway"


def test_scan_missing_root_returns_empty(tmp_path) -> None:
    assert scan(tmp_path / "nope", "svc") == []


@pytest.mark.parametrize("field", ["version", "protocol"])
def test_scan_requires_string_fields(tmp_path, field) -> None:
    _write_card(tmp_path, "demo", _card(**{field: 1}))
    assert scan(tmp_path, "svc") == []


def test_scan_skips_reserved_dir_names_even_with_valid_cards(tmp_path) -> None:
    _write_card(tmp_path, "platform", _card(name="platform-trap"))
    _write_card(tmp_path, "host", _card(name="host-trap"))
    _write_card(tmp_path, "real", _card())
    assert [c.domain for c in scan(tmp_path, "svc")] == ["real"]


def test_scan_skips_invalid_name_and_status(tmp_path, caplog) -> None:
    _write_card(tmp_path, "bad_name", _card(name=123))
    _write_card(tmp_path, "bad_status", _card(status=["x"]))
    with caplog.at_level(logging.WARNING):
        assert scan(tmp_path, "svc") == []
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_sources_card_does_not_declare_test_hooks() -> None:
    """clone_fn / parse_fn are wire() kwargs, not shared facilities on the card."""
    root = Path(__file__).resolve().parents[3] / "packages"
    sources = next(c for c in scan(root, "packages") if c.domain == "sources")
    assert "clone_fn" not in sources.needs
    assert "parse_fn" not in sources.needs
    assert "workspace" in sources.needs
