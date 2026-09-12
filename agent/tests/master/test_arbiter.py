"""Tests for message arbitration: queue by default, AUTO asks a judge LLM to
merge, GUIDE queues with a notification.
"""

from agent.llm import FakeLLM, LLMReply
from agent.master.arbiter import Arbiter, ArbiterMode


class TestArbiter:
    async def test_queue_default_no_llm_call(self) -> None:
        llm = FakeLLM()
        arbiter = Arbiter(llm)
        d = await arbiter.decide("new message", "current task", mode=ArbiterMode.QUEUE)
        assert d.action == "enqueue"
        assert llm.calls == []  # queue mode consumes no judge tokens

    async def test_auto_merge_when_related(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="merge")]))
        d = await arbiter.decide(
            "addendum: use Python 3.12", "analyze the project", mode=ArbiterMode.AUTO
        )
        assert d.action == "merge"

    async def test_auto_enqueue_when_new_intent(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="enqueue")]))
        d = await arbiter.decide(
            "make me a slide deck", "analyze the project", mode=ArbiterMode.AUTO
        )
        assert d.action == "enqueue"

    async def test_guide_notifies_on_new_intent(self) -> None:
        arbiter = Arbiter(FakeLLM([LLMReply(text="enqueue")]))
        d = await arbiter.decide(
            "make me a slide deck", "analyze the project", mode=ArbiterMode.GUIDE
        )
        assert d.action == "enqueue_notify"
        assert "do this first" in d.reason
