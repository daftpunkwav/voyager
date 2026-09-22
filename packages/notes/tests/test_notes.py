"""Tests for the notes service: CRUD, summary/full two-level loading, linking,
events, state machine, version history, wiki links, and search enhancements.
"""

from pathlib import Path

import pytest
from notes.capabilities import Deps, init_deps, registry
from notes.settings import DEFS
from notes.store import NoteStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef, ServiceError
from platform_eventbus import EventBus, EventLog
from platform_settings import SettingsStore

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def deps(tmp_path):
    log = EventLog(tmp_path / "events.db")
    bus = EventBus(log)
    store = NoteStore(tmp_path / "notes.db", history_keep=5)
    settings = SettingsStore(tmp_path / "settings.db", bus)
    settings.register_fresh(DEFS)
    init_deps(Deps(store=store, bus=bus, settings=settings, workspace=tmp_path))
    yield store, log
    store.close()
    log.close()
    settings.close()


class TestCrud:
    async def test_create_and_get(self, deps) -> None:
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "learn langgraph", "content": "# outline\npoints", "tags": ["agent"]},
        )
        assert note["id"]
        full = await execute(registry, "get_note", AGENT_CTX, {"note_id": note["id"]})
        assert full["content"].startswith("# outline")  # agents read with user-level parity

    async def test_rejects_illegal_source_id(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "create_note",
                USER_CTX,
                {"title": "bad source_id", "source_id": "../etc/passwd"},
            )
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_update_and_events(self, deps) -> None:
        _, log = deps
        note = await execute(registry, "create_note", USER_CTX, {"title": "t"})
        await execute(
            registry, "update_note", USER_CTX, {"note_id": note["id"], "content": "new body"}
        )
        types = [e.type for _, e in log.read_after()]
        assert types == ["note.created", "note.edited"]


class TestSessionAttribution:
    async def test_events_carry_chat_session_inside_a_turn(self, deps) -> None:
        """The agent runtime stamps the executing chat session; session-filtered
        consumers (chat history, SSE lanes) route on it."""
        from platform_capability import current_chat_session

        _, log = deps
        token = current_chat_session.set("sess-abc")
        try:
            await execute(registry, "create_note", AGENT_CTX, {"title": "from chat"})
        finally:
            current_chat_session.reset(token)
        (_, event), *_ = log.read_after()
        assert event.payload["session"] == "sess-abc"

    async def test_events_stay_session_less_outside_a_turn(self, deps) -> None:
        """REST / UI / import paths have no chat context: no session key."""
        _, log = deps
        await execute(registry, "create_note", USER_CTX, {"title": "outside chat"})
        (_, event), *_ = log.read_after()
        assert "session" not in event.payload

    async def test_delete_moves_to_trash_and_restore(self, deps) -> None:
        """Soft-delete semantics: delete moves to trash (recoverable); purge removes for good."""
        _, log = deps
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "to-delete", "content": "body"}
        )
        nid = note["id"]
        await execute(registry, "delete_note", USER_CTX, {"note_id": nid})
        trashed = await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert trashed["trashed_ts"] is not None  # trashed notes are still readable by id
        await execute(registry, "restore_note", USER_CTX, {"note_id": nid})
        back = await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert back["trashed_ts"] is None
        await execute(registry, "purge_note", USER_CTX, {"note_id": nid})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "get_note", USER_CTX, {"note_id": nid})
        assert exc.value.body.code == "NOTES.NOT_FOUND"
        types = [e.type for _, e in log.read_after()]
        for expected in ("note.created", "note.deleted", "note.restored", "note.purged"):
            assert expected in types

    async def test_empty_trash_batch_purges_and_emits_once(self, deps) -> None:
        _, log = deps
        a = await execute(registry, "create_note", USER_CTX, {"title": "a"})
        b = await execute(registry, "create_note", USER_CTX, {"title": "b"})
        await execute(registry, "delete_note", USER_CTX, {"note_id": a["id"]})
        await execute(registry, "delete_note", USER_CTX, {"note_id": b["id"]})
        out = await execute(registry, "empty_trash", USER_CTX, {})
        assert out["purged_count"] == 2
        types = [e.type for _, e in log.read_after()]
        assert types.count("note.purged_batch") == 1
        assert types.count("note.purged") == 0
        listed = await execute(registry, "list_notes", USER_CTX, {"state": "trash"})
        assert listed == []

    async def test_delete_twice_conflict(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "x"})
        await execute(registry, "delete_note", USER_CTX, {"note_id": note["id"]})
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "delete_note", USER_CTX, {"note_id": note["id"]})
        assert exc.value.body.code == "NOTES.CONFLICT"

    async def test_list_summary_truncates_content(self, deps) -> None:
        store, _ = deps
        store.create({"title": "long note", "content": "c" * 500})
        out = await execute(registry, "list_notes", USER_CTX, {})
        assert "content" not in out[0]  # listings never return full content
        assert len(out[0]["excerpt"]) == 120

    async def test_list_filter_by_tag_and_source(self, deps) -> None:
        await execute(
            registry, "create_note", USER_CTX, {"title": "a", "tags": ["x"], "source_id": "s1"}
        )
        await execute(registry, "create_note", USER_CTX, {"title": "b", "tags": ["y"]})
        assert len(await execute(registry, "list_notes", USER_CTX, {"tag": "x"})) == 1
        assert len(await execute(registry, "list_notes", USER_CTX, {"source_id": "s1"})) == 1


class TestStatesAndSearch:
    async def test_state_views_exclude_each_other(self, deps) -> None:
        n1 = await execute(registry, "create_note", USER_CTX, {"title": "plain"})
        n2 = await execute(registry, "create_note", USER_CTX, {"title": "archived-item"})
        await execute(registry, "update_note", USER_CTX, {"note_id": n2["id"], "archived": True})
        await execute(registry, "delete_note", USER_CTX, {"note_id": n1["id"]})

        active = await execute(registry, "list_notes", USER_CTX, {})
        archived = await execute(registry, "list_notes", USER_CTX, {"state": "archived"})
        trash = await execute(registry, "list_notes", USER_CTX, {"state": "trash"})
        everything = await execute(registry, "list_notes", USER_CTX, {"state": "all"})
        assert active == []  # archived and trashed notes stay out of the default view
        assert {n["title"] for n in archived} == {"archived-item"}
        assert {n["title"] for n in trash} == {"plain"}
        assert len(everything) == 2
        assert archived[0]["archived"] is True

    async def test_query_search_escaped_wildcard(self, deps) -> None:
        await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "progress100%", "content": "no keyword here"},
        )
        hits = await execute(registry, "list_notes", USER_CTX, {"query": "100%"})
        assert len(hits) == 1  # % is not a wildcard; unescaped it would over-match
        assert await execute(registry, "list_notes", USER_CTX, {"query": "nomatch"}) == []

    async def test_pin_sorting(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX, {"title": "first"})
        second = await execute(registry, "create_note", USER_CTX, {"title": "second"})
        await execute(registry, "update_note", USER_CTX, {"note_id": second["id"], "pinned": True})
        listing = await execute(registry, "list_notes", USER_CTX, {"sort": "created"})
        assert listing[0]["pinned"] is True
        assert listing[0]["title"] == "second"


class TestTagsEnhanced:
    async def test_list_tags_counts_excludes_trash(self, deps) -> None:
        a = await execute(
            registry, "create_note", USER_CTX, {"title": "a", "tags": ["rust", "study"]}
        )
        await execute(registry, "create_note", USER_CTX, {"title": "b", "tags": ["study"]})
        await execute(registry, "delete_note", USER_CTX, {"note_id": a["id"]})
        tags = {t["tag"]: t["count"] for t in await execute(registry, "list_tags", USER_CTX, {})}
        assert tags == {"study": 1}

    async def test_rename_tag_globally(self, deps) -> None:
        await execute(registry, "create_note", USER_CTX, {"title": "a", "tags": ["js", "frontend"]})
        b = await execute(registry, "create_note", USER_CTX, {"title": "b", "tags": ["js"]})
        out = await execute(registry, "rename_tag", USER_CTX, {"old": "js", "new": "typescript"})
        assert out["affected"] == 2
        tags_b = (await execute(registry, "get_note", USER_CTX, {"note_id": b["id"]}))["tags"]
        assert tags_b == ["typescript"]

    async def test_rename_tag_does_not_substring_match(self, deps) -> None:
        """Renaming tag 'a' must not touch 'ab'; element matching is exact."""
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "substring", "tags": ["a", "ab"]}
        )
        out = await execute(registry, "rename_tag", USER_CTX, {"old": "a", "new": "x"})
        assert out["affected"] == 1
        tags = (await execute(registry, "get_note", USER_CTX, {"note_id": note["id"]}))["tags"]
        assert tags == ["x", "ab"]

    async def test_stats_counts(self, deps) -> None:
        a = await execute(registry, "create_note", USER_CTX, {"title": "s1"})
        await execute(registry, "update_note", USER_CTX, {"note_id": a["id"], "archived": True})
        await execute(registry, "create_note", USER_CTX, {"title": "s2"})
        stats = await execute(registry, "notes_stats", USER_CTX, {})
        assert stats["active"] == 1 and stats["archived"] == 1 and stats["total"] == 2


class TestVersions:
    async def test_content_changes_snapshot_and_restore(self, deps) -> None:
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "v-note", "content": "first draft"}
        )
        nid = note["id"]
        await execute(
            registry, "update_note", USER_CTX, {"note_id": nid, "content": "second draft"}
        )
        await execute(
            registry, "update_note", USER_CTX, {"note_id": nid, "content": "second draft"}
        )  # identical content does not re-snapshot
        versions = (await execute(registry, "list_versions", USER_CTX, {"note_id": nid}))[
            "versions"
        ]
        assert [v["version"] for v in versions] == [1]
        snap = await execute(registry, "read_version", USER_CTX, {"note_id": nid, "version": 1})
        assert snap["content"] == "first draft"
        restored = await execute(
            registry, "restore_version", USER_CTX, {"note_id": nid, "version": 1}
        )
        assert restored["content"] == "first draft"  # current content rolled back
        again = await execute(registry, "list_versions", USER_CTX, {"note_id": nid})
        assert again["versions"][0]["version"] == 2  # the restore itself creates a new snapshot

    async def test_history_keep_cap(self, deps) -> None:
        store, _ = deps
        nid = store.create({"title": "freq", "content": "0"})
        for i in range(1, 10):
            store.update(nid, content=f"v{i} draft")  # history_keep=5
        versions = store.list_versions(nid)
        assert [v["version"] for v in versions] == [9, 8, 7, 6, 5]


class TestBacklinks:
    async def test_link_sync_and_backlink_view(self, deps) -> None:
        target = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "target-page", "content": "the linked page"},
        )
        await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "ref-page", "content": "see [[target-page]] and [[missing-page]]"},
        )
        links = (await execute(registry, "get_backlinks", USER_CTX, {"note_id": target["id"]}))[
            "backlinks"
        ]
        assert [link["title"] for link in links] == ["ref-page"]

    async def test_links_dropped_on_purge(self, deps) -> None:
        src = await execute(
            registry, "create_note", USER_CTX, {"title": "src", "content": "see [[dst-page]]"}
        )
        dst = await execute(registry, "create_note", USER_CTX, {"title": "dst-page"})
        await execute(registry, "purge_note", USER_CTX, {"note_id": src["id"]})
        remaining = (await execute(registry, "get_backlinks", USER_CTX, {"note_id": dst["id"]}))[
            "backlinks"
        ]
        assert remaining == []


class TestExportAndLinkFields:
    async def test_export_note_writes_markdown(self, deps, tmp_path) -> None:
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": 'expo"rt/name', "content": "# body\ntext", "tags": ["t1"]},
        )
        out = await execute(registry, "export_note", USER_CTX, {"note_id": note["id"]})
        path = tmp_path / "workspace" / "notes-export" / Path(out["path"]).name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n") and "# body" in text
        assert "/" not in path.name and '"' not in path.name  # filename sanitized

    async def test_link_note_clears_with_empty_string(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "n", "source_id": "src1"})
        cleared = await execute(
            registry, "link_note", USER_CTX, {"note_id": note["id"], "source_id": ""}
        )
        assert cleared["source_id"] == ""

    async def test_agent_parity_write(self, deps) -> None:
        """Agents create and edit notes with the same rights as users."""
        note = await execute(
            registry, "create_note", AGENT_CTX, {"title": "agent created", "content": "parity"}
        )
        updated = await execute(
            registry, "update_note", AGENT_CTX, {"note_id": note["id"], "pinned": True}
        )
        assert updated["pinned"] is True


class TestBatchNotes:
    async def test_batch_archive_delete_export(self, deps, tmp_path) -> None:
        a = await execute(registry, "create_note", USER_CTX, {"title": "first", "content": "a"})
        b = await execute(registry, "create_note", USER_CTX, {"title": "second", "content": "b"})
        ids = [a["id"], b["id"]]
        archived = await execute(
            registry, "batch_notes", USER_CTX, {"ids": ids, "action": "archive"}
        )
        assert archived["count"] == 2 and archived["failed"] == []
        listed = await execute(registry, "list_notes", USER_CTX, {"state": "archived"})
        assert {n["id"] for n in listed} == set(ids)

        restored = await execute(
            registry, "batch_notes", AGENT_CTX, {"ids": ids, "action": "unarchive"}
        )
        assert restored["count"] == 2

        exported = await execute(
            registry, "batch_notes", USER_CTX, {"ids": ids, "action": "export"}
        )
        assert len(exported["paths"]) == 2
        for p in exported["paths"]:
            assert Path(p).exists()

        trashed = await execute(registry, "batch_notes", USER_CTX, {"ids": ids, "action": "delete"})
        assert trashed["count"] == 2
        trash = await execute(registry, "list_notes", USER_CTX, {"state": "trash"})
        assert {n["id"] for n in trash} == set(ids)

    async def test_batch_partial_failure_and_validation(self, deps) -> None:
        live = await execute(registry, "create_note", USER_CTX, {"title": "live"})
        out = await execute(
            registry,
            "batch_notes",
            USER_CTX,
            {
                "ids": [live["id"], "missing-id", live["id"]],
                "action": "pin",
            },
        )
        assert out["ok"] == [live["id"]]
        assert len(out["failed"]) == 1
        assert out["failed"][0]["id"] == "missing-id"
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry, "batch_notes", USER_CTX, {"ids": [live["id"]], "action": "explode"}
            )
        assert exc.value.body.code == "NOTES.INVALID_INPUT"
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "batch_notes", USER_CTX, {"ids": live["id"], "action": "pin"})
        assert exc.value.body.code == "NOTES.INVALID_INPUT"


class TestNotesView:
    async def test_get_defaults(self, deps) -> None:
        view = await execute(registry, "get_notes_view", USER_CTX, {})
        assert view["font_size"] == 15
        assert view["mode"] == "edit"
        assert view["layout"] == "list"
        assert view["sync_scroll"] is True
        assert view["list_state"] == "active"
        assert view["sort"] == "updated"
        assert view["filter"] == "all"
        assert view["query"] == ""
        assert view["source_id"] == ""
        assert view["panel"] == "none"
        assert view["density"] == "comfortable"
        assert view["toc_width"] == 188
        assert view["persisted"] is True

    async def test_user_and_agent_same_write(self, deps) -> None:
        """A user clicking "preview / A+" and an agent calling set_notes_view
        write the same settings.
        """
        _, log = deps
        user = await execute(
            registry, "set_notes_view", USER_CTX, {"mode": "preview", "font_delta": 2}
        )
        assert user["mode"] == "preview"
        assert user["font_size"] == 17
        agent = await execute(
            registry, "set_notes_view", AGENT_CTX, {"mode": "edit", "font_size": 13}
        )
        assert agent["mode"] == "edit" and agent["font_size"] == 13
        stored = await execute(registry, "get_notes_view", AGENT_CTX, {})
        assert stored["mode"] == "edit" and stored["font_size"] == 13
        types = [e.type for _, e in log.read_after()]
        assert types.count("notes.ui.changed") >= 2

    async def test_ui_event_only_carries_changed_fields(self, deps) -> None:
        _, log = deps
        await execute(registry, "set_notes_view", USER_CTX, {"mode": "split"})
        events = [e for _, e in log.read_after() if e.type == "notes.ui.changed"]
        payload = events[-1].payload
        assert payload["mode"] == "split"
        assert "font_size" not in payload

    async def test_open_note_and_index(self, deps) -> None:
        note = await execute(registry, "create_note", USER_CTX, {"title": "open-me"})
        opened = await execute(
            registry, "set_notes_view", AGENT_CTX, {"note_id": note["id"], "mode": "preview"}
        )
        assert opened["action"] == "open" and opened["note_id"] == note["id"]
        back = await execute(registry, "set_notes_view", USER_CTX, {"index": True})
        assert back["action"] == "index" and back["note_id"] is None

    async def test_rejects_bad_mode(self, deps) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "set_notes_view", USER_CTX, {"mode": "zen"})
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_font_delta_clamps(self, deps) -> None:
        await execute(registry, "set_notes_view", USER_CTX, {"font_size": 24})
        out = await execute(registry, "set_notes_view", AGENT_CTX, {"font_delta": 5})
        assert out["font_size"] == 24

    async def test_sort_filter_panel_same_write(self, deps) -> None:
        user = await execute(
            registry,
            "set_notes_view",
            USER_CTX,
            {"sort": "created", "filter": "untitled", "density": "compact", "panel": "trash"},
        )
        assert user["sort"] == "created"
        assert user["filter"] == "untitled"
        assert user["density"] == "compact"
        assert user["panel"] == "trash"
        agent = await execute(
            registry,
            "set_notes_view",
            AGENT_CTX,
            {"filter": "today", "query": "architecture", "panel": "none"},
        )
        assert agent["filter"] == "today" and agent["query"] == "architecture"
        assert agent["panel"] == "none"
        stored = await execute(registry, "get_notes_view", USER_CTX, {})
        assert stored["sort"] == "created" and stored["filter"] == "today"
        assert stored["query"] == "architecture" and stored["density"] == "compact"

    async def test_toc_width_user_and_agent_same_write(self, deps) -> None:
        user = await execute(registry, "set_notes_view", USER_CTX, {"toc_width": 260})
        assert user["toc_width"] == 260
        agent = await execute(registry, "set_notes_view", AGENT_CTX, {"toc_width": 900})
        assert agent["toc_width"] == 480
        stored = await execute(registry, "get_notes_view", USER_CTX, {})
        assert stored["toc_width"] == 480
        too_narrow = await execute(registry, "set_notes_view", AGENT_CTX, {"toc_width": 10})
        assert too_narrow["toc_width"] == 148

    async def test_assist_not_persisted(self, deps) -> None:
        _, log = deps
        out = await execute(registry, "set_notes_view", AGENT_CTX, {"assist": True})
        assert out["assist"] is True
        events = [e for _, e in log.read_after() if e.type == "notes.ui.changed"]
        assert events[-1].payload.get("assist") is True
        stored = await execute(registry, "get_notes_view", USER_CTX, {})
        assert "assist" not in stored or stored.get("assist") is not True

    async def test_quote_not_persisted(self, deps) -> None:
        _, log = deps
        out = await execute(
            registry, "set_notes_view", AGENT_CTX, {"quote": "  middleware\nlayer  "}
        )
        assert out["quote"] == "middleware layer" and out["assist"] is True
        events = [e for _, e in log.read_after() if e.type == "notes.ui.changed"]
        assert events[-1].payload.get("quote") == "middleware layer"
        stored = await execute(registry, "get_notes_view", USER_CTX, {})
        assert "quote" not in stored
        desc = registry.get("set_notes_view").description
        assert "Miyai" not in desc
        assert "scout persona" in desc


class TestMigration:
    async def test_legacy_db_upgrades_with_defaults(self, tmp_path) -> None:
        """A legacy schema (no archived/pinned/trashed_ts) gains the missing columns
        on open with data preserved.
        """
        import sqlite3

        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE notes (
                id TEXT PRIMARY KEY, title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
                source_id TEXT NOT NULL DEFAULT '', node_id TEXT NOT NULL DEFAULT '',
                created_ts REAL NOT NULL, updated_ts REAL NOT NULL);
            INSERT INTO notes VALUES ('old1','old note','content','[]','','',1,2);
        """)
        conn.commit()
        conn.close()
        store = NoteStore(db)
        note = store.get("old1")
        assert note is not None
        assert note["title"] == "old note"
        assert note["archived"] is False and note["pinned"] is False
        assert note["trashed_ts"] is None
        store.close()


class TestRetention:
    async def test_purge_expired_respects_retention(self, deps) -> None:
        """retention=0 never purges; only expired entries are removed."""
        import time as _t

        store, _ = deps
        a = store.create({"title": "old", "content": ""})
        b = store.create({"title": "new", "content": ""})
        store.trash(a)
        store.trash(b)
        old = _t.time() - 31 * 86400
        store._conn.execute("UPDATE notes SET trashed_ts=? WHERE id=?", (old, a))
        store._conn.commit()
        assert store.purge_expired(0) == []  # 0 = keep forever
        assert store.purge_expired(30) == [a]  # only the expired note is purged
        assert store.get(a) is None and store.get(b) is not None


class TestRenderAndEditSupport:
    async def test_toc_extracts_headings_skip_fence(self, deps) -> None:
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {
                "title": "outline",
                "content": "# One\nbody\n## Two\n```py\n# not a heading\n```\n### Three",
            },
        )
        toc = (await execute(registry, "get_note_toc", USER_CTX, {"note_id": note["id"]}))["toc"]
        assert [(t["level"], t["text"]) for t in toc] == [(1, "One"), (2, "Two"), (3, "Three")]
        assert toc[0]["line"] == 1 and toc[1]["line"] == 3

    async def test_resolve_links_detail_with_dangling(self, deps) -> None:
        target = await execute(
            registry, "create_note", USER_CTX, {"title": "existing-page", "content": ""}
        )
        src = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "src", "content": "[[existing-page]] and [[ghost-page]]"},
        )
        out = await execute(registry, "resolve_links", USER_CTX, {"note_id": src["id"]})
        by_raw = {i["raw"]: i for i in out["links"]}
        assert by_raw["existing-page"]["target_id"] == target["id"]
        assert by_raw["ghost-page"]["target_id"] is None
        assert out["resolved"] == 1 and out["unresolved"] == 1

    async def test_wiki_link_no_crossline_capture(self, deps) -> None:
        """[[ never spans lines: [[across\nlines]] must not merge two lines into one target."""
        src = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "across-lines-src", "content": "[[across\nlines]]"},
        )
        out = await execute(registry, "resolve_links", USER_CTX, {"note_id": src["id"]})
        assert all(i["raw"] != "across\nlines" for i in out["links"])

    async def test_edit_note_range_bold_selection(self, deps) -> None:
        """Atomic range edit: the bold-selection flow backed by the frontend toolbar."""
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "selection", "content": "this has bold-me inside"},
        )
        start = note["content"].index("bold-me")
        end = start + len("bold-me")
        updated = await execute(
            registry,
            "edit_note_range",
            USER_CTX,
            {"note_id": note["id"], "start": start, "end": end, "new_text": "**bold-me**"},
        )
        assert updated["content"] == "this has **bold-me** inside"
        versions = (await execute(registry, "list_versions", USER_CTX, {"note_id": note["id"]}))[
            "versions"
        ]
        assert len(versions) == 1  # range edits also enter version history

    async def test_edit_note_range_out_of_bounds(self, deps) -> None:
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "boundary", "content": "abc"}
        )
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "edit_note_range",
                USER_CTX,
                {"note_id": note["id"], "start": 0, "end": 99, "new_text": "x"},
            )
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_mark_note_span_user_and_agent_same_write(self, deps) -> None:
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "底纹", "content": "先看中间件再看编排"}
        )
        user = await execute(
            registry,
            "mark_note_span",
            USER_CTX,
            {"note_id": note["id"], "quote": "中间件", "tone": "cool"},
        )
        assert user["content"] == "先看==cool:中间件==再看编排"
        agent = await execute(
            registry,
            "mark_note_span",
            AGENT_CTX,
            {"note_id": note["id"], "quote": "中间件", "tone": "rose"},
        )
        assert agent["content"] == "先看==rose:中间件==再看编排"
        again = await execute(
            registry,
            "mark_note_span",
            AGENT_CTX,
            {"note_id": note["id"], "quote": "中间件", "tone": "rose"},
        )
        assert again["content"] == agent["content"]
        cleared = await execute(
            registry,
            "mark_note_span",
            USER_CTX,
            {"note_id": note["id"], "quote": "中间件", "tone": "clear"},
        )
        assert cleared["content"] == "先看中间件再看编排"

    async def test_mark_note_span_skips_fenced_code(self, deps) -> None:
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "fence", "content": "```\nhello\n```\n\nhello body"},
        )
        out = await execute(
            registry,
            "mark_note_span",
            USER_CTX,
            {"note_id": note["id"], "quote": "hello", "tone": "warm"},
        )
        assert out["content"].startswith("```\nhello\n```")
        assert "==warm:hello== body" in out["content"]

    async def test_mark_note_span_missing_quote(self, deps) -> None:
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "empty", "content": "only these words"}
        )
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "mark_note_span",
                USER_CTX,
                {"note_id": note["id"], "quote": "missing", "tone": "warm"},
            )
        assert exc.value.body.code == "NOTES.INVALID_INPUT"

    async def test_mark_note_span_multiline_wraps_per_line(self, deps) -> None:
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "multiline", "content": "第一段\n\n第二段"}
        )
        out = await execute(
            registry,
            "mark_note_span",
            USER_CTX,
            {"note_id": note["id"], "quote": "第一段\n\n第二段", "tone": "cool"},
        )
        assert out["content"] == "==cool:第一段==\n\n==cool:第二段=="
        listed = await execute(
            registry, "create_note", USER_CTX, {"title": "list", "content": "- aa\n- bb"}
        )
        marked = await execute(
            registry,
            "mark_note_span",
            AGENT_CTX,
            {"note_id": listed["id"], "quote": "- aa\n- bb", "tone": "rose"},
        )
        assert marked["content"] == "- ==rose:aa==\n- ==rose:bb=="

    async def test_import_note_front_matter(self, deps, tmp_path) -> None:
        f = tmp_path / "in.md"
        f.write_text(
            "---\ntitle: imported-title\ntags: [a, b]\n---\n# body\ntable\n", encoding="utf-8"
        )
        imported = await execute(registry, "import_note", USER_CTX, {"file_path": str(f)})
        assert imported["title"] == "imported-title"
        assert imported["tags"] == ["a", "b"]
        assert imported["content"].startswith("# body")
        # Explicit arguments override the front-matter title.
        retitled = await execute(
            registry, "import_note", USER_CTX, {"file_path": str(f), "title": "override-title"}
        )
        assert retitled["title"] == "override-title"

    async def test_import_note_rejects_outside_workspace(self, deps, tmp_path) -> None:
        outsider = tmp_path.parent / f"{tmp_path.name}-outside.md"
        outsider.write_text("# secret\n", encoding="utf-8")
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "import_note", USER_CTX, {"file_path": str(outsider)})
        assert exc.value.body.code == "NOTES.FORBIDDEN"

    async def test_import_note_outside_missing_is_forbidden(self, deps, tmp_path) -> None:
        """A missing file outside the jail also returns FORBIDDEN, so path existence
        is never disclosed.
        """
        ghost = tmp_path.parent / f"{tmp_path.name}-ghost.md"
        assert not ghost.exists()
        with pytest.raises(ServiceError) as exc:
            await execute(registry, "import_note", USER_CTX, {"file_path": str(ghost)})
        assert exc.value.body.code == "NOTES.FORBIDDEN"

    async def test_crlf_normalized_on_write(self, deps) -> None:
        note = await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "linebreaks", "content": "line1\r\nline2\r\nline3"},
        )
        assert "\r" not in note["content"]
        await execute(
            registry, "update_note", USER_CTX, {"note_id": note["id"], "content": "x\r\ny"}
        )
        got = await execute(registry, "get_note", USER_CTX, {"note_id": note["id"]})
        assert got["content"] == "x\ny"

    async def test_query_excerpt_shows_hit_window(self, deps) -> None:
        filler = "前置文字" * 30  # push the hit well past the first 120 chars
        await execute(
            registry,
            "create_note",
            USER_CTX,
            {"title": "长文命中窗口", "content": filler + "命中词在这里附近"},
        )
        hits = await execute(registry, "list_notes", USER_CTX, {"query": "命中词"})
        assert len(hits) == 1
        excerpt = hits[0]["excerpt"]
        assert excerpt.index("命中词") > 50  # the hit sits mid-window, not at a fixed prefix

    async def test_validation_title_and_tag(self, deps) -> None:
        with pytest.raises(ServiceError):
            await execute(registry, "create_note", USER_CTX, {"title": "   "})
        with pytest.raises(ServiceError):
            await execute(registry, "rename_tag", USER_CTX, {"old": 'a"b', "new": "c"})


class TestRegistryCard:
    def test_service_json_matches_registry(self) -> None:
        """The service card capability list must match the registry (single source of truth)."""
        import json as _json
        from pathlib import Path as _Path

        from notes.assets import register as register_assets

        register_assets(registry)
        card = _json.loads(
            (_Path(__file__).parent.parent / "service.json").read_text(encoding="utf-8")
        )
        assert set(card["capabilities"]) == set(registry.names())
