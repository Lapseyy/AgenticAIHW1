import json
import sys
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BROKEN_SERVER = str(Path(__file__).parent / "fake_servers" / "broken_server.py")


@pytest.fixture
def workspace(tmp_path, monkeypatch) -> Path:
    """Point the filesystem server at a fresh temp directory."""
    path = tmp_path / "workspace"
    path.mkdir()
    monkeypatch.setenv("WORKSPACE_DIR", str(path))
    return path


@pytest.fixture
def write_config(tmp_path):
    """Write an MCP manifest built from the named server entries and return its path."""
    entries = {
        "filesystem": {"transport": "stdio", "command": "mcp-server-filesystem", "args": ["${WORKSPACE_DIR}"]},
        "fetch": {"transport": "stdio", "command": "${PYTHON}", "args": ["-m", "mcp_server_fetch"]},
        "broken": {"transport": "stdio", "command": "${PYTHON}", "args": [BROKEN_SERVER]},
        "garbage": {"transport": "stdio", "command": "${PYTHON}", "args": [BROKEN_SERVER, "--garbage"]},
        "missing": {"transport": "stdio", "command": "/nonexistent/mcp-server", "args": []},
    }

    def _write(*names: str) -> str:
        path = tmp_path / "mcp_config.json"
        path.write_text(json.dumps({name: entries[name] for name in names}))
        return str(path)

    return _write


class ScriptedChatModel(BaseChatModel):
    """Stand-in LLM that replays scripted AIMessages and records what it was sent.

    Lets the graph, the real MCP tool calls, and the memory layer be tested
    without an API key. Once the script runs out, `default` is returned.
    """

    script: list[AIMessage] = []
    default: AIMessage = AIMessage(content="ok")
    seen: list[list] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        message = self.script.pop(0) if self.script else self.default
        # Fresh copy each time: reusing one message object (same id) would overwrite history.
        return ChatResult(generations=[ChatGeneration(message=message.model_copy(deep=True, update={"id": None}))])

    @property
    def _llm_type(self) -> str:
        return "scripted"


def tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])
