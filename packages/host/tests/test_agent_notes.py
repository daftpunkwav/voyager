"""Agent note-writing integration: a FakeLLM script calls notes__create_note
and the note is persisted and a note.created event is published.
"""

import time

from agent.llm import FakeLLM, LLMReply, ToolCall
from fastapi.testclient import TestClient
from host.assemble import build
from platform_contracts import DomainEvent


class TestAgentWritesNotes:
    def test_create_note_via_bridge(self, tmp_path) -> None:
        """Conversation-driven agent creates a note via a domain capability:
        event plus summary listing, and the LLM receives the artifact id."""
        script = [
            LLMReply(
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="notes__create_note",
                        arguments={
                            "title": "ReAct essentials",
                            "content": "Sense-Act loop.",
                            "tags": ["methodology"],
                        },
                    ),
                )
            ),
            LLMReply(text="Noted."),
        ]
        llm = FakeLLM(script)
        app = build(tmp_path / "data", tmp_path / "ws", llm=llm)
        backend = app.state.backend
        with TestClient(app) as client:
            client.post("/api/chat/messages", json={"content": "note down the ReAct essentials"})

            # note.created event (reliable signal that the agent persisted it)
            deadline = time.time() + 8
            created = []
            while time.time() < deadline:
                created = [e for _, e in backend.log.read_after(types=["note.created"])]
                if created:
                    break
                time.sleep(0.05)
            assert created, "note.created not published"
            note_id = created[-1].payload["note_id"]
            assert created[-1].payload["title"] == "ReAct essentials"

            # Summary listing is visible (data source of the user-facing notes
            # page; summaries without content is part of the contract)
            out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
            mine = next(s for s in out if s["id"] == note_id)
            assert mine["title"] == "ReAct essentials"
            assert mine["tags"] == ["methodology"]
            assert "content" not in mine

            # Agent finishes with a reply and the tool result carries the artifact
            # id (lets the conversation point the user to it); the reply lands a
            # beat after note.created, so poll for it rather than assume timing
            replies: list = []
            deadline = time.time() + 8
            while time.time() < deadline:
                replies = [
                    e
                    for _, e in backend.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
                    if e.payload.get("content") == "Noted."
                ]
                if replies:
                    break
                time.sleep(0.05)
            assert replies
            tool_result_messages = llm.calls[1]["messages"]
            assert any(note_id in str(m.get("content", "")) for m in tool_result_messages)
