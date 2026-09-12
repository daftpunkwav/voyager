"""End-to-end chat integration: gateway HTTP entry -> event stream -> agent
loop -> LLM (FakeLLM script).

Covers message roundtrip, the ask_user dialog roundtrip (the answer is fed back
and the LLM receives it), and queue arbitration (a second message sent while one
is executing is queued and processed after completion).
"""

import asyncio
import time

from agent.llm import FakeLLM, LLMReply, ToolCall
from fastapi.testclient import TestClient
from host.assemble import build
from platform_contracts import DomainEvent

_AGENT_MSG = [DomainEvent.AGENT_MESSAGE]


def _wait_event(log, types, *, timeout=8.0, pred=None):
    """Poll the event log until an event matching the condition appears (agent
    processing is asynchronous)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        events = [e for _, e in log.read_after(types=types) if pred is None or pred(e)]
        if events:
            return events
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for events: {types}")


class TestChatFlow:
    def test_message_roundtrip(self, tmp_path) -> None:
        """User POST -> user.message -> agent processing -> agent.message (non-empty)."""
        llm = FakeLLM(default="Got it, I'm here.")
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            resp = client.post("/api/chat/messages", json={"content": "ok"})
            assert resp.status_code == 200
            assert resp.json()["seq"] > 0

            users = _wait_event(backend.log, [DomainEvent.USER_MESSAGE])
            assert users[-1].payload["content"] == "ok"

            agents = _wait_event(backend.log, _AGENT_MSG)
            assert agents[-1].payload["content"] == "Got it, I'm here."

            # History endpoint (used when a page reopens) shows both directions
            hist = client.get("/api/chat/messages?limit=10").json()["messages"]
            kinds = {m["type"] for m in hist}
            assert {"user.message", "agent.message"} <= kinds

    def test_ask_user_roundtrip(self, tmp_path) -> None:
        """LLM calls ask_user -> agent.ask event -> answer_question feeds the
        answer back -> the LLM receives it and finishes."""
        script = [
            LLMReply(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="ask_user",
                        arguments={"prompt": "pick one", "kind": "choice", "options": ["A", "B"]},
                    ),
                )
            ),
            LLMReply(text="You picked A."),
        ]
        llm = FakeLLM(script)
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "ask me a question"})
            asks = _wait_event(backend.log, ["agent.ask"])
            ask = asks[-1]
            assert ask.payload["kind"] == "choice"
            assert ask.payload["options"] == ["A", "B"]

            qid = ask.payload["question_id"]
            out = client.post(
                "/api/agent/capabilities/answer_question", json={"question_id": qid, "value": "A"}
            ).json()
            assert out["result"]["matched"] is True

            # The second LLM call's messages should contain the user's answer,
            # followed by the closing reply
            replies = _wait_event(
                backend.log, _AGENT_MSG, pred=lambda e: e.payload.get("content") == "You picked A."
            )
            assert replies
            second_messages = llm.calls[1]["messages"]
            assert any("A" in str(m.get("content", "")) for m in second_messages)

    def test_queue_mode_second_message_waits(self, tmp_path) -> None:
        """Queue arbitration really queues: while the first message is still on
        the LLM, the second is only enqueued and does not start a new complete;
        after completion both replies land in the log in order.

        The first reply first produces a real Action (request_context) before
        finishing: a zero-tool plain-text non-greeting is treated as non-final by
        the continuation semantics, so the window assertions and reply texts are
        chosen to steer around that rule.
        """
        calls: list[float] = []

        async def dynamic(messages, tools):
            calls.append(time.monotonic())
            if len(calls) == 1:
                await asyncio.sleep(1.0)  # slow first call to create an "executing" window
                return LLMReply(
                    tool_calls=(
                        ToolCall(
                            "c1",
                            "request_context",
                            {"need": "context"},
                        ),
                    )
                )
            if len(calls) == 2:
                return LLMReply(text="first one done.")
            return LLMReply(text="second one done.")

        app = build(tmp_path / "data", tmp_path / "ws", llm=FakeLLM(dynamic=dynamic))
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "first one"})
            # Poll until the first message enters the LLM call (agent processes
            # asynchronously, timing is not deterministic)
            deadline = time.time() + 3.0
            while time.time() < deadline and not calls:
                time.sleep(0.02)
            assert calls, "first message was never processed"
            client.post("/api/chat/messages", json={"content": "second one"})
            # The first is still inside the LLM sleep window: in queue mode the
            # second neither interrupts nor interjects
            assert len(calls) == 1

            _wait_event(
                backend.log,
                _AGENT_MSG,
                pred=lambda e: e.payload.get("content") == "first one done.",
            )
            _wait_event(
                backend.log,
                _AGENT_MSG,
                pred=lambda e: e.payload.get("content") == "second one done.",
            )
            # Sequential processing: the second reply's seq comes after the first
            seqs = [
                (s, e)
                for s, e in backend.log.read_after(types=_AGENT_MSG)
                if e.payload.get("content") in ("first one done.", "second one done.")
            ]
            assert [e.payload["content"] for _, e in seqs] == [
                "first one done.",
                "second one done.",
            ]
