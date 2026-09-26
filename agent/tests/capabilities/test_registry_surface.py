"""Domain capability REST surface: agent and human invoke the same
capability with the same standing."""

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from platform_actor import ActorContext
from platform_contracts import LOCAL_USER, ActorKind, ActorRef

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


class TestRegistrySurface:
    async def test_capability_names_frozen(self, app) -> None:
        assert app.registry.names() == [
            "add_mcp_server",
            "agent_instance",
            "answer_question",
            "approve_mcp_tools",
            "board",
            "context",
            "extension",
            "get_settings",
            "goal",
            "jobs",
            "list_personas",
            "list_skills",
            "memory",
            "observe",
            "plan",
            "rate_turn",
            "remove_mcp_server",
            "report_page_context",
            "session",
            "set_plugin_approval",
            "set_setting",
            "skill",
            "subagent",
            "taskboard",
            "todowrite",
            "tools",
        ]
