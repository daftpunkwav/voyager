"""Job cancellation router: a projected job routes to its source domain's
own cancel capability through the late-bound call; unknown domain / missing
capability give actionable errors, never guesses."""

from __future__ import annotations

import pytest
from host.jobs_router import make_job_cancel_router
from platform_contracts import ServiceError


class _FakeView:
    def __init__(self, jobs: dict) -> None:
        self.jobs = jobs

    def find(self, job_id: str):
        return self.jobs.get(job_id)


def _call_factory(calls: list):
    async def call(domain: str, name: str, args: dict):
        calls.append((domain, name, args))
        return {"cancelled": args.get("job_id")}

    return call


class TestRouter:
    async def test_routes_to_source_domain_capability(self) -> None:
        calls: list = []
        view = _FakeView({"j-1": {"job_id": "j-1", "source": "graph", "kind": "index"}})
        out = await make_job_cancel_router(_call_factory(calls), view)("j-1")
        assert out == {"cancelled": "j-1"}
        assert calls == [("graph", "cancel_index", {"job_id": "j-1"})]

    async def test_unknown_job_and_uncancellable_domain(self) -> None:
        view = _FakeView({"j-9": {"job_id": "j-9", "source": "notes", "kind": "x"}})
        with pytest.raises(ServiceError) as exc:
            await make_job_cancel_router(_call_factory([]), view)("missing")
        assert "no such background job" in exc.value.body.message
        with pytest.raises(ServiceError) as exc:
            await make_job_cancel_router(_call_factory([]), view)("j-9")
        assert "no cancel capability" in exc.value.body.message
