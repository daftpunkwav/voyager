"""Interact capability group (human -> agent reply and context channels).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.interact.answer_question import register as _answer_question
from agent.capabilities.interact.report_page_context import register as _report_page_context


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _report_page_context(reg, deps)
    _answer_question(reg, deps)
