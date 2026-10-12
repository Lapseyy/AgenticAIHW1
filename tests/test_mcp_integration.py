"""Real MCP traffic: tools/list and tools/call against live stdio servers, plus the
three failure modes from assignment section 3.3. No LLM needed."""

import asyncio

import pytest

import mcp_client
from mcp_client import discover_tools


def discover(config_path):
    tools, statuses = asyncio.run(discover_tools(config_path))
    return {tool.name: tool for tool in tools}, {status.name: status for status in statuses}


def call(tool, args: dict):
    """Invoke a tool the way LangGraph's ToolNode does, returning the ToolMessage."""
    return asyncio.run(tool.ainvoke({"name": tool.name, "args": args, "id": "test-call", "type": "tool_call"}))


def test_tools_list_discovers_both_real_servers(workspace, write_config):
    tools, statuses = discover(write_config("filesystem", "fetch"))
    assert statuses["filesystem"].ok and statuses["fetch"].ok
    assert {"write_file", "read_text_file", "fetch"} <= tools.keys()
    # The JSON Schema from tools/list becomes the tool's argument schema.
    assert tools["write_file"].args_schema["required"] == ["path", "content"]


def test_tools_call_round_trip_through_filesystem_server(workspace, write_config):
    tools, _ = discover(write_config("filesystem"))
    target = str(workspace / "notes.txt")
    assert call(tools["write_file"], {"path": target, "content": "hello mcp"}).status == "success"
    assert (workspace / "notes.txt").read_text() == "hello mcp"
    assert "hello mcp" in call(tools["read_text_file"], {"path": target}).text


def test_tool_execution_error_is_returned_not_raised(workspace, write_config):
    tools, _ = discover(write_config("filesystem"))
    result = call(tools["read_text_file"], {"path": "/etc/passwd"})
    assert result.status == "error"
    assert "outside allowed directories" in result.text


def test_unreachable_server_is_skipped_and_others_still_load(workspace, write_config):
    tools, statuses = discover(write_config("missing", "filesystem"))
    assert not statuses["missing"].ok
    assert statuses["filesystem"].ok and "write_file" in tools


def test_server_that_speaks_garbage_is_skipped(workspace, write_config):
    tools, statuses = discover(write_config("garbage", "filesystem"))
    assert not statuses["garbage"].ok
    assert statuses["filesystem"].ok


def test_bad_config_file_does_not_crash(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json")
    tools, statuses = asyncio.run(discover_tools(str(path)))
    assert tools == [] and statuses[0].ok is False


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        ("bad_shape", "invalid response"),  # malformed result, fails CallToolResult validation
        ("audio", "cannot read"),  # valid MCP, unsupported content block
        ("crash", "unavailable"),  # server process dies mid-call (transport closed)
    ],
)
def test_broken_tool_responses_become_error_messages(workspace, write_config, monkeypatch, tool_name, expected):
    monkeypatch.setattr(mcp_client, "TOOL_CALL_TIMEOUT_S", 10)
    tools, statuses = discover(write_config("broken"))
    assert statuses["broken"].ok
    result = call(tools[tool_name], {})
    assert result.status == "error"
    assert expected in result.text
