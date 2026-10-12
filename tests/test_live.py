"""End-to-end checks with the real LLM and real MCP servers.

Skipped unless OPENAI_API_KEY is set (they cost a few cents). Run with:
    pytest tests/test_live.py -v
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


def tools_used(graph, session_id) -> list[str]:
    state = asyncio.run(graph.aget_state({"configurable": {"thread_id": session_id}}))
    return [m.name for m in state.values["messages"] if isinstance(m, ToolMessage)]


@pytest.fixture(scope="module")
def graph():
    return asyncio.run(build_agent(CONFIG))[0]


def test_no_tool_for_general_knowledge(graph):
    answer = asyncio.run(run_turn(graph, "In one sentence, what is a binary search tree?", "live-no-tool"))
    assert answer
    assert tools_used(graph, "live-no-tool") == []


def test_filesystem_tools_for_file_request(graph):
    asyncio.run(run_turn(graph, "Create a file called hello.txt containing 'hi from the agent', then read it back.", "live-fs"))
    assert "write_file" in tools_used(graph, "live-fs")
    assert (Path(workspace_dir()) / "hello.txt").exists()


def test_memory_across_turns(graph):
    asyncio.run(run_turn(graph, "My favorite data structure is the heap. Just acknowledge.", "live-mem"))
    answer = asyncio.run(run_turn(graph, "What is my favorite data structure?", "live-mem"))
    assert "heap" in answer.lower()
