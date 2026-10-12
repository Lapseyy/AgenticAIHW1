"""MCP client wrapper.

Loads the MCP server manifest (mcp_config.json), runs `tools/list` against
each server to discover its tools, and wraps every `tools/call` with failure
handling so a broken server never crashes the agent.

Failure modes handled (assignment section 3.3):
  1. Connection/transport failures  -> server skipped at startup, or the
     tool call returns an error message to the LLM.
  2. Tool execution errors (isError) -> passed back to the LLM as an error
     ToolMessage by langchain-mcp-adapters (handle_tool_errors=True).
  3. Malformed/invalid responses     -> JSON-RPC/schema validation errors and
     unsupported content blocks become an error message to the LLM.
"""

import asyncio
import json
import logging
import os
import string
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from mcp.types import CallToolResult, EmbeddedResource, ImageContent, ResourceLink, TextContent

logger = logging.getLogger(__name__)

DISCOVERY_TIMEOUT_S = float(os.getenv("MCP_DISCOVERY_TIMEOUT", "30"))
TOOL_CALL_TIMEOUT_S = float(os.getenv("MCP_TOOL_TIMEOUT", "60"))
SUPPORTED_CONTENT = (TextContent, ImageContent, EmbeddedResource, ResourceLink)


@dataclass
class ServerStatus:
    """Result of tool discovery for one MCP server (shown on GET /health)."""

    name: str
    ok: bool
    tools: list[str] = field(default_factory=list)
    error: str | None = None


def workspace_dir() -> str:
    """Absolute path of the directory the filesystem server is allowed to touch."""
    path = Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


class _EnvVars(dict):
    """Template variables: unset variables expand to "" instead of raising."""

    def __missing__(self, key: str) -> str:
        return ""


def _expand(value, variables: _EnvVars):
    """Recursively expand ${VAR} placeholders inside the parsed config."""
    if isinstance(value, str):
        return string.Template(value).substitute(variables)
    if isinstance(value, list):
        return [_expand(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item, variables) for key, item in value.items()}
    return value


def load_config(path: str) -> dict:
    """Read the server manifest and fill in ${VAR} placeholders from the environment.

    Secrets such as TAVILY_API_KEY stay in the environment, never in the JSON file.
    ${PYTHON} resolves to the running interpreter so the Python fetch server uses
    the same environment (venv locally, /usr/local in Docker).
    """
    variables = _EnvVars(os.environ)
    variables["PYTHON"] = sys.executable
    variables["WORKSPACE_DIR"] = workspace_dir()
    return _expand(json.loads(Path(path).read_text()), variables)


def _error_result(message: str) -> CallToolResult:
    """An MCP-style error result; the adapter turns it into an error ToolMessage."""
    return CallToolResult(content=[TextContent(type="text", text=message)], isError=True)


async def guard_tool_call(request: MCPToolCallRequest, handler) -> CallToolResult:
    """Interceptor around every MCP tools/call.

    Logs the call, enforces a timeout, and converts transport failures and
    malformed responses into error results the LLM can read and explain,
    instead of exceptions that would abort the whole request.
    """
    server, tool = request.server_name, request.name
    logger.info("tools/call -> %s.%s args=%s", server, tool, request.args)
    try:
        result = await asyncio.wait_for(handler(request), TOOL_CALL_TIMEOUT_S)
    except TimeoutError:
        logger.warning("tools/call timeout: %s.%s", server, tool)
        return _error_result(f"The '{server}' server did not answer within {TOOL_CALL_TIMEOUT_S:.0f}s.")
    except Exception as exc:  # transport closed, process died, invalid JSON-RPC, schema mismatch
        logger.warning("tools/call failed: %s.%s: %r", server, tool, exc)
        return _error_result(
            f"The '{server}' MCP server is unavailable or returned an invalid response "
            f"({type(exc).__name__}). The tool '{tool}' could not run."
        )

    if not isinstance(result, CallToolResult):
        return _error_result(f"The '{server}' server returned an unexpected response type.")
    unsupported = sorted({type(block).__name__ for block in result.content if not isinstance(block, SUPPORTED_CONTENT)})
    if unsupported:
        logger.warning("tools/call %s.%s returned unsupported content: %s", server, tool, unsupported)
        return _error_result(f"The '{server}' server returned content this agent cannot read: {', '.join(unsupported)}.")

    logger.info("tools/call <- %s.%s isError=%s blocks=%d", server, tool, result.isError, len(result.content))
    return result


async def discover_tools(config_path: str) -> tuple[list[BaseTool], list[ServerStatus]]:
    """Run tools/list on every configured server.

    A server that fails to start, times out, or answers with garbage is skipped
    and reported in its ServerStatus; the remaining servers still load.
    """
    try:
        connections = load_config(config_path)
    except (OSError, ValueError) as exc:
        logger.error("Could not load MCP config %s: %s", config_path, exc)
        return [], [ServerStatus(name="config", ok=False, error=str(exc))]

    client = MultiServerMCPClient(connections, tool_interceptors=[guard_tool_call])
    tools: list[BaseTool] = []
    statuses: list[ServerStatus] = []
    seen_names: set[str] = set()

    for name in connections:
        try:
            server_tools = await asyncio.wait_for(client.get_tools(server_name=name), DISCOVERY_TIMEOUT_S)
        except Exception as exc:
            logger.error("tools/list failed for '%s': %r", name, exc)
            statuses.append(ServerStatus(name=name, ok=False, error=type(exc).__name__))
            continue

        unique = [tool for tool in server_tools if tool.name not in seen_names]
        if len(unique) < len(server_tools):
            logger.warning("'%s' has tool names already used by another server; duplicates skipped", name)
        seen_names.update(tool.name for tool in unique)
        tools.extend(unique)
        statuses.append(ServerStatus(name=name, ok=True, tools=[tool.name for tool in unique]))
        logger.info("tools/list '%s': %d tools %s", name, len(unique), [tool.name for tool in unique])

    return tools, statuses


def status_report(statuses: list[ServerStatus]) -> list[dict]:
    return [asdict(status) for status in statuses]
