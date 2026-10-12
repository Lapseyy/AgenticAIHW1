"""Graph behavior with a scripted LLM and the real filesystem MCP server:
tool chaining, no-tool answers, session memory, and the loop guard."""

import asyncio

import pytest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

import agent
from agent import STOPPED_MESSAGE, build_graph, run_turn
from mcp_client import discover_tools
from conftest import ScriptedChatModel, tool_call


def make_graph(llm, config_path=None):
    tools = asyncio.run(discover_tools(config_path))[0] if config_path else []
    return build_graph(llm, tools)


def history(graph, session_id):
    state = asyncio.run(graph.aget_state({"configurable": {"thread_id": session_id}}))
    return state.values["messages"]


def test_agent_chains_two_tool_calls(workspace, write_config):
    path = str(workspace / "plan.md")
    llm = ScriptedChatModel(script=[
        tool_call("write_file", {"path": path, "content": "step one"}, "c1"),
        tool_call("read_text_file", {"path": path}, "c2"),
        AIMessage(content="Saved and verified: step one"),
    ])
    graph = make_graph(llm, write_config("filesystem"))

    answer = asyncio.run(run_turn(graph, "Save 'step one' to plan.md and read it back", "s1"))

    assert answer == "Saved and verified: step one"
    tool_results = [m for m in history(graph, "s1") if isinstance(m, ToolMessage)]
    assert [m.name for m in tool_results] == ["write_file", "read_text_file"]
    assert "step one" in tool_results[1].text  # the LLM's second step saw the real file content
    assert (workspace / "plan.md").read_text() == "step one"


def test_agent_answers_without_tools_when_none_are_needed(workspace, write_config):
    llm = ScriptedChatModel(script=[AIMessage(content="A stack is LIFO; a queue is FIFO.")])
    graph = make_graph(llm, write_config("filesystem"))
    answer = asyncio.run(run_turn(graph, "Stack vs queue?", "s1"))
    assert "LIFO" in answer
    assert not any(isinstance(m, ToolMessage) for m in history(graph, "s1"))


def test_memory_is_kept_per_session_and_isolated_between_sessions():
    llm = ScriptedChatModel(script=[])
    graph = make_graph(llm)

    asyncio.run(run_turn(graph, "My name is Edmarck.", "alice"))
    asyncio.run(run_turn(graph, "What is my name?", "alice"))
    asyncio.run(run_turn(graph, "What is my name?", "bob"))

    second_turn_alice, first_turn_bob = llm.seen[1], llm.seen[2]
    human_text = lambda msgs: [m.content for m in msgs if isinstance(m, HumanMessage)]
    assert human_text(second_turn_alice) == ["My name is Edmarck.", "What is my name?"]
    assert human_text(first_turn_bob) == ["What is my name?"]


# Odd limit: stops right after the LLM asks for a tool (unanswered tool call is repaired).
# Even limit: stops right after a tool result.
@pytest.mark.parametrize("limit", [5, 6])
def test_loop_guard_stops_runaway_tool_calls_and_session_stays_usable(workspace, write_config, monkeypatch, limit):
    monkeypatch.setattr(agent, "RECURSION_LIMIT", limit)
    llm = ScriptedChatModel(script=[], default=tool_call("list_allowed_directories", {}, "loop"))
    graph = make_graph(llm, write_config("filesystem"))

    assert asyncio.run(run_turn(graph, "Do something forever", "s1")) == STOPPED_MESSAGE

    last = history(graph, "s1")[-1]
    assert isinstance(last, AIMessage) and last.content == STOPPED_MESSAGE  # turn closed cleanly
    llm.default = AIMessage(content="Back to normal.")
    assert asyncio.run(run_turn(graph, "Hello again", "s1")) == "Back to normal."
