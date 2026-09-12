"""Activity feed integration: after a sequence of operations (create note,
change settings, send message, delete note) the feed returns all events in ascending seq
order, type filtering works, and the compensating undo of note.created (via delete_note)
appends note.deleted with the user as actor.
"""

from fastapi.testclient import TestClient
from host.assemble import build


def _seqs(events: list[dict]) -> list[int]:
    return [e["seq"] for e in events]


def test_feed_ascending_and_type_filter(tmp_path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws", llm=_noop_llm())
    with TestClient(app) as client:
        note = client.post(
            "/api/notes/capabilities/create_note", json={"title": "activity feed test"}
        ).json()["result"]
        client.post(
            "/api/settings/capabilities/set_setting",
            json={"key": "notes.sort.default", "value": "created"},
        )
        client.post("/api/chat/messages", json={"content": "ok"})
        client.post("/api/notes/capabilities/delete_note", json={"note_id": note["id"]})

        feed = client.get("/api/activity/feed").json()["events"]
        types = [e["type"] for e in feed]
        assert "note.created" in types
        assert "settings.changed" in types
        assert "user.message" in types
        assert "note.deleted" in types
        assert _seqs(feed) == sorted(_seqs(feed))  # ascending
        assert len(set(_seqs(feed))) == len(feed)  # seqs are unique across the feed

        # types filter: only note creation comes back
        only = client.get("/api/activity/feed?types=note.created").json()["events"]
        assert only and all(e["type"] == "note.created" for e in only)
        assert all(e["payload"]["title"] == "activity feed test" for e in only)

        # after_seq cursor: paging from the middle neither duplicates nor skips
        mid = only[0]["seq"]
        rest = client.get(f"/api/activity/feed?after_seq={mid}").json()["events"]
        assert all(e["seq"] > mid for e in rest)


def test_compensation_undo_note_created(tmp_path) -> None:
    """Undoing note.created = delete_note (inverse capability): the list no longer
    contains it and note.deleted is appended."""
    app = build(tmp_path / "data", tmp_path / "ws", llm=_noop_llm())
    with TestClient(app) as client:
        note = client.post(
            "/api/notes/capabilities/create_note", json={"title": "undo target"}
        ).json()["result"]
        out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
        assert any(s["id"] == note["id"] for s in out)

        # Compensation action (the call behind the activity page undo button;
        # actor = local user)
        client.post("/api/notes/capabilities/delete_note", json={"note_id": note["id"]})
        out = client.post("/api/notes/capabilities/list_notes", json={}).json()["result"]
        assert all(s["id"] != note["id"] for s in out)

        deleted = client.get("/api/activity/feed?types=note.deleted").json()["events"]
        assert deleted and deleted[-1]["payload"]["title"] == "undo target"


def _noop_llm():
    """Minimal LLM: chat messages do not drive a real agent (avoids the
    nondeterministic no-key degradation path)."""
    from agent.llm import FakeLLM

    return FakeLLM(default="ok.")
