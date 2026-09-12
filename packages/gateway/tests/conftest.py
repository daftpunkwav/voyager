"""Assemble a test gateway (mounting an in-memory echo service)."""

import pytest
from gateway.mounts import MountSpec
from gateway.rest import create_app
from platform_capability import Registry, capability
from platform_eventbus import EventBus, EventLog

_echo_registry = Registry("echo")


@capability(_echo_registry, name="echo", description="echo back")
def echo(text: str) -> dict:
    return {"text": text}


@capability(_echo_registry, name="explode", description="must fail")
def explode() -> dict:
    from platform_contracts import ErrorSuffix, ServiceError

    raise ServiceError("echo", ErrorSuffix.UNAVAILABLE, "echo service is down")


@pytest.fixture()
def echo_registry():
    """The mounted echo registry, for tests that assemble their own app."""
    return _echo_registry


@pytest.fixture()
def bus(tmp_path):
    return EventBus(EventLog(tmp_path / "events.db"))


@pytest.fixture()
def app(bus, tmp_path):
    return create_app(
        [MountSpec(domain="echo", registry=_echo_registry, probe=lambda: {"status": "up"})],
        bus=bus,
        db_path=tmp_path / "gw.db",
    )
