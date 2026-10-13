"""HTTP contract for POST /chat and GET /health, including error responses."""

import httpx
import openai
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

import main
from agent import build_graph
from conftest import ScriptedChatModel
from mcp_client import ServerStatus


@pytest.fixture
def client():
    # No `with` block, so the startup hook (real tool discovery + real LLM) is skipped.
    main.app.state.agent = build_graph(ScriptedChatModel(script=[AIMessage(content="Hi there!")]), [])
    main.app.state.mcp_status = [ServerStatus(name="filesystem", ok=True, tools=["read_file"])]
    return TestClient(main.app)


def failing_agent(error: Exception):
    class FailingGraph:
        async def ainvoke(self, *args, **kwargs):
            raise error

        async def aget_state(self, config):
            return type("State", (), {"values": {}})()

    return FailingGraph()


def test_chat_returns_response_field(client):
    reply = client.post("/chat", json={"query": "hello", "session_id": "s1"})
    assert reply.status_code == 200
    assert reply.json() == {"response": "Hi there!"}


@pytest.mark.parametrize("body", [{"session_id": "s1"}, {"query": "hi"}, {"query": "", "session_id": "s1"}])
def test_invalid_request_is_rejected_with_422(client, body):
    assert client.post("/chat", json=body).status_code == 422


def test_unexpected_error_returns_clean_json(client):
    main.app.state.agent = failing_agent(RuntimeError("boom"))
    reply = client.post("/chat", json={"query": "hello", "session_id": "s1"})
    assert reply.status_code == 500
    assert "something went wrong" in reply.json()["response"]


def test_llm_rate_limit_returns_503(client):
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    main.app.state.agent = failing_agent(openai.RateLimitError("slow down", response=response, body=None))
    reply = client.post("/chat", json={"query": "hello", "session_id": "s1"})
    assert reply.status_code == 503
    assert "rate-limited" in reply.json()["response"]


def test_root_explains_the_api(client):
    body = client.get("/").json()
    assert "/chat" in body["chat"]


def test_health_lists_mcp_servers(client):
    body = client.get("/health").json()
    assert body["mcp_servers"][0]["name"] == "filesystem"