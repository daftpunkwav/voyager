"""Capability definitions and input validation.

Responsibilities:
- capability(): decorator turning a handler into a registered Capability
  (name, cost, reversibility, long_running)
- coerce_input: build and shallow-check the dataclass input model

Handler conventions:
- With an input_model (dataclass), the handler receives **one** constructed
  model instance.
- Without one, the handler receives the raw inputs as **kwargs.
- Returns dict / dataclass / JobRef (required when long_running).
"""

from __future__ import annotations

import dataclasses
import re
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

Handler = Callable[..., Any]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class Capability:
    """Capability metadata. The description is written for the LLM: when to
    use the capability and what it returns."""

    name: str
    description: str
    handler: Handler
    input_model: type | None = None
    cost: int = 1  # quota deduction tier; quota only, not used for write classification
    reversible: bool = True
    write: bool = True  # write capability (explicit, not derived from cost); bridges pass through
    scopes: frozenset[str] = frozenset()  # required scopes; empty = no extra requirement
    long_running: bool = False  # when True the handler must return JobRef (enqueue only)
    # Streaming capability: the handler returns AsyncIterator[dict], consumable
    # in-process only; the REST channel rejects it outright (a generator cannot
    # be JSON-serialized), and execute validates this contract.
    streaming: bool = False
    # Agent-side policy dimension when the bridge mounts this capability as a
    # tool ("app" by default; "network" for capabilities that fetch URLs, so
    # the agent-facing fetch obeys the same network policy as the native tools).
    dimension: str = "app"


def capability(
    registry,
    *,
    name: str,
    description: str,
    input_model: type | None = None,
    cost: int = 1,
    reversible: bool = True,
    write: bool = True,
    scopes: typing.Iterable[str] = (),
    long_running: bool = False,
    streaming: bool = False,
    dimension: str = "app",
) -> Callable[[Handler], Handler]:
    """Decorator: register a function as a capability in the registry."""
    if not _NAME_RE.match(name):
        raise ServiceError(
            registry.domain,
            ErrorSuffix.INVALID_INPUT,
            f"capability name must be lowercase snake_case: {name!r}",
        )

    def decorator(fn: Handler) -> Handler:
        registry.register(
            Capability(
                name=name,
                description=description,
                handler=fn,
                input_model=input_model,
                cost=cost,
                reversible=reversible,
                write=write,
                scopes=frozenset(scopes),
                long_running=long_running,
                streaming=streaming,
                dimension=dimension,
            )
        )
        return fn

    return decorator


def _type_name(expected: Any) -> str:
    return getattr(expected, "__name__", str(expected))


def _check_shallow(domain: str, name: str, value: Any, expected: Any) -> None:
    """Shallow type check: constrains primitive types only; composite,
    Optional, and Any are left to the handler."""
    if expected is bool:
        ok = isinstance(value, bool)
    elif expected is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif expected is float:
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected is str:
        ok = isinstance(value, str)
    elif expected is list:
        ok = isinstance(value, list)
    elif expected is dict:
        ok = isinstance(value, dict)
    else:
        return  # not a primitive: no framework-level enforcement
    if not ok:
        raise ServiceError(
            domain,
            ErrorSuffix.INVALID_INPUT,
            f"input {name} should be {_type_name(expected)}, got {type(value).__name__}",
        )


def coerce_input(model: type | None, data: Any, *, domain: str) -> Any:
    """Validate the input dict and build an input_model instance; returns the
    data unchanged when there is no model."""
    if model is None:
        return data if data is not None else {}
    if not isinstance(data, dict):
        raise ServiceError(domain, ErrorSuffix.INVALID_INPUT, "input must be a JSON object")
    hints = typing.get_type_hints(model)
    fields = {f.name: f for f in dataclasses.fields(model)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ServiceError(
            domain, ErrorSuffix.INVALID_INPUT, f"unknown inputs: {', '.join(unknown)}"
        )
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, f in fields.items():
        if name in data:
            value = data[name]
            if name in hints:
                _check_shallow(domain, name, value, hints[name])
            kwargs[name] = value
        elif f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            missing.append(name)
    if missing:
        raise ServiceError(
            domain, ErrorSuffix.INVALID_INPUT, f"missing required inputs: {', '.join(missing)}"
        )
    try:
        return model(**kwargs)
    except TypeError as exc:
        raise ServiceError(
            domain, ErrorSuffix.INVALID_INPUT, f"failed to build input: {exc}"
        ) from exc
