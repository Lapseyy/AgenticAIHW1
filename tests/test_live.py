"""End-to-end checks with the real LLM and real MCP servers.

Skipped unless OPENAI_API_KEY is set (in the environment or .env). Run with:
    pytest tests/test_live.py -v

All tests here share ONE event loop, the same way the server runs under uvicorn.
langchain-openai caches a single HTTP client for the whole process, and its open
connections belong to the loop that created them. Running each test in its own
asyncio.run() would close that loop and make the next test fail with
"Event loop is closed".
"""

import asyncio
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage

from agent import build_agent, run_turn
from mcp_client import workspace_dir

load_dotenv()
pytestmark = pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY")
CONFIG = os.path.join(os.path.dirname(__file__), "..", "mcp_config.json")


@pytest.fixture(scope="module")
def run():
    """One event loop for every live test; `run(coro)` executes a coroutine on it."""
    with asyncio.Runner() as runner:
        yield runner.run


@pytest.fixture(scope="module")
def graph(run):
    return run(build_agent(CONFIG))[0]


def tools_used(run, graph, session_id: str) -> list[str]:
    state = run(graph.aget_state({"configurable": {"thread_id": session_id}}))
    return [m.name for m in state.values["messages"] if isinstance(m, ToolMessage)]


def test_no_tool_for_general_knowledge(run, graph):
    answer = run(run_turn(graph, "In one sentence, what is a binary search tree?", "live-no-tool"))
    assert answer
    assert tools_used(run, graph, "live-no-tool") == []


def test_filesystem_tools_for_file_request(run, graph):
    target = Path(workspace_dir()) / "hello.txt"
    target.unlink(missing_ok=True)  # make sure the agent really creates it
    run(run_turn(graph, "Create a file called hello.txt containing 'hi from the agent', then read it back.", "live-fs"))
    assert "write_file" in tools_used(run, graph, "live-fs")
    assert target.exists()


def test_memory_across_turns(run, graph):
    run(run_turn(graph, "My favorite data structure is the heap. Just acknowledge.", "live-mem"))
    answer = run(run_turn(graph, "What is my favorite data structure?", "live-mem"))
    assert "heap" in answer.lower()