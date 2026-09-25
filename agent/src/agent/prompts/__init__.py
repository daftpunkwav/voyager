"""Central LLM prompt assets: TOML data files exposed as the `P` prompt tree.

Prompts live in ``definitions/*.toml`` (one top-level table per file, the
domain) and are never authored inside business code. Modules read composed
text as ``P.modes.cot.synthesis`` and fill runtime values with
``render(P.modes.cot.plan, max_steps=12)``.

Composition rules:
- a value may be written as an array of lines; the loader joins the elements
  with newlines into one text block (consumers needing the individual items
  back call ``splitlines()`` — no item may itself contain a newline);
- an array element starting with ``@common.`` pulls in that block from
  ``common.toml``. References point into the ``common`` table only, so the
  domain -> base direction is enforced by the loader and cycles are
  impossible; a dangling or cross-domain reference is a load-time error.

``{placeholder}`` tokens stay in the data and are substituted only at the
call site: the placeholder pattern requires an identifier right after the
brace, so JSON examples embedded in a prompt (``{"score": ...}``) are never
touched by ``render()``.

Responsibilities:
- load every ``definitions/*.toml`` at import, fail loudly on duplicate
  domains, unknown references, or non-text values, and freeze the tree
- expose the composed tree behind ``P`` (unknown keys raise AttributeError)
- provide ``render()`` with strict missing/unused value checks
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"
_REF_PREFIX = "@common."
_MAX_REF_DEPTH = 8
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class PromptNode:
    """Read-only attribute view over one TOML table; leaves are text."""

    __slots__ = ("_values",)

    def __init__(self, values: dict[str, Any]) -> None:
        object.__setattr__(self, "_values", values)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._values[name]
        except KeyError:
            raise AttributeError(f"unknown prompt: {name!r}") from None


def _resolve_ref(item: str, common: dict[str, Any], path: str, depth: int) -> str:
    """One ``@common.a.b`` element -> the composed text of that block."""
    node: Any = common
    for part in item[len(_REF_PREFIX) :].split("."):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"{path}: unknown common reference {item!r}")
        node = node[part]
    composed = _compose(node, common, f"{path} -> {item}", depth + 1)
    if not isinstance(composed, str):
        raise ValueError(f"{path}: common reference {item!r} must resolve to text")
    return composed


def _compose(value: Any, common: dict[str, Any], path: str, depth: int = 0) -> Any:
    """Compose one raw value: strings pass through, arrays join their lines
    (resolving common-block references); anything else is an authoring error."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if depth > _MAX_REF_DEPTH:
            raise ValueError(f"{path}: block reference nesting too deep")
        lines: list[str] = []
        for item in value:
            if isinstance(item, str) and item.startswith(_REF_PREFIX):
                lines.append(_resolve_ref(item, common, path, depth))
            elif isinstance(item, str):
                lines.append(item)
            else:
                raise ValueError(f"{path}: array elements must be strings")
        return "\n".join(lines)
    raise ValueError(f"{path}: prompt values must be strings or arrays of strings")


def _build() -> tuple[PromptNode, dict[str, Any]]:
    files = sorted(_DEFINITIONS_DIR.glob("*.toml"))
    if not files:
        raise ValueError(f"no prompt definitions found in {_DEFINITIONS_DIR}")
    raw: dict[str, Any] = {}
    for path in files:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        for domain, table in data.items():
            if domain in raw:
                raise ValueError(f"{path.name}: prompt domain {domain!r} defined twice")
            raw[domain] = table
    common = raw.get("common")
    if not isinstance(common, dict):
        raise ValueError("common.toml with a [common] table is required")

    def freeze(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            return PromptNode({k: freeze(v, f"{path}.{k}") for k, v in value.items()})
        return _compose(value, common, path)

    return PromptNode({domain: freeze(table, domain) for domain, table in raw.items()}), raw


P, _RAW = _build()


def render(template: str, /, **values: Any) -> str:
    """Substitute ``{placeholder}`` tokens with runtime values.

    A placeholder without a matching keyword and a keyword never used by the
    template are both errors, so template/value drift fails loudly instead of
    shipping a prompt with a literal ``{name}`` in it.
    """
    used: set[str] = set()

    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise ValueError(f"missing render value: {key!r}")
        used.add(key)
        return str(values[key])

    out = _PLACEHOLDER.sub(sub, template)
    unused = set(values) - used
    if unused:
        raise ValueError(f"unused render values: {sorted(unused)}")
    return out


__all__ = ["P", "render"]
