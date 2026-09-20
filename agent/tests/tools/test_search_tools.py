"""Tests for the search_tools capability: lexical scoring over the roster,
empty/whitespace queries, limit handling, and the live registry binding."""

from agent.capabilities.tools.tools import rank_tools

_ROSTER = [
    {"name": "notes__create_note", "description": "新建一条笔记"},
    {"name": "web_search", "description": "Search the web for pages"},
    {"name": "read", "description": "Read a file from disk"},
]


def test_name_hits_outrank_description_hits() -> None:
    out = rank_tools(_ROSTER, "web")
    assert out[0]["name"] == "web_search"
    assert out[0]["score"] >= 2  # name hit weighs more


def test_multi_term_query_matches_description() -> None:
    out = rank_tools(_ROSTER, "笔记")
    assert [e["name"] for e in out] == ["notes__create_note"]


def test_no_match_returns_empty() -> None:
    assert rank_tools(_ROSTER, "zk-Stanmoor") == []


def test_empty_query_returns_empty() -> None:
    assert rank_tools(_ROSTER, "") == []
    assert rank_tools(_ROSTER, "   ") == []


def test_limit_caps_results() -> None:
    out = rank_tools(_ROSTER, "e", limit=1)  # "e" hits every entry somewhere
    assert len(out) == 1


async def test_registry_binding_returns_scored_hits(tmp_path) -> None:
    from agent.build import build_agent
    from agent.llm import FakeLLM
    from platform_actor import ActorContext
    from platform_capability import execute
    from platform_contracts import LOCAL_USER

    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    try:
        hits = await execute(
            app.registry,
            "tools",
            ActorContext(actor=LOCAL_USER),
            {"action": "search", "query": "todo"},
        )
        names = [h["name"] for h in hits]
        assert "todowrite" in names and "todowrite" in names
    finally:
        app.memory.close()
