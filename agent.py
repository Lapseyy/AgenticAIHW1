"""LangGraph agent: a reason -> act loop over MCP tools, with per-session memory.

Graph:  START -> agent --(tool calls?)--> tools -> agent ... --(no tool calls)--> END

Memory: a MemorySaver checkpointer stores each conversation's messages under
thread_id = session_id, so turns in the same session see earlier turns and
different sessions never share state. It lives in process memory, so it is
lost when the Cloud Run instance stops (allowed by the assignment).
"""

import logging
import os
from datetime import date

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from mcp_client import discover_tools, workspace_dir

logger = logging.getLogger(__name__)

# Each tool round trip uses 2 graph steps (agent + tools), so 16 allows ~7 tool calls per turn.
RECURSION_LIMIT = int(os.getenv("AGENT_RECURSION_LIMIT", "16"))
STOPPED_MESSAGE = "I stopped because this request needed too many tool calls. Try breaking it into smaller steps."

SYSTEM_PROMPT = """You are a helpful assistant that can work with files and the web.

Decide for every request whether a tool is actually needed:
- General knowledge, explanations, math, coding help, or questions about this conversation: answer directly. Do not call tools.
- Reading, writing, listing or searching files: use the filesystem tools. Every path must be an absolute path inside {workspace}.
- Current events, recent releases, or facts you are unsure about: use web search.
- The user gives a URL, or you need the full text of one page: use fetch.

Some requests need several tools in sequence (for example: search, then fetch a result, then save notes to a file). Keep going until the whole request is done.
If a tool returns an error or is unavailable, tell the user briefly what failed and continue with whatever you can still do. Never invent tool results.
You remember earlier messages in this conversation; use them when the user refers back.
Today's date is {today}. When searching for current or latest information, do not add years to the query unless the user asked for them."""


def build_llm() -> BaseChatModel:
    """Chat model for the agent. ChatOpenAI reads OPENAI_API_KEY and OPENAI_BASE_URL
    from the environment, so the same code works for OpenAI and NVIDIA NIM."""
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return ChatOpenAI(model=os.getenv("MODEL_NAME", "gpt-5"), timeout=90, max_retries=2)


def _tool_error_message(error: Exception) -> str:
    """Last line of defense: any exception inside a tool becomes a message the LLM can read."""
    logger.warning("Tool raised %r", error)
    return f"Tool failed ({type(error).__name__}): {error}. Explain the failure to the user and continue without this result."


def build_graph(llm: BaseChatModel, tools: list[BaseTool], checkpointer=None):
    """Compile the agent state graph. With no tools it simply answers from the LLM."""
    model = llm.bind_tools(tools) if tools else llm

    async def call_model(state: MessagesState) -> dict:
        system = SystemMessage(SYSTEM_PROMPT.format(workspace=workspace_dir(), today=date.today().isoformat()))
        response = await model.ainvoke([system, *state["messages"]])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_edge(START, "agent")
    if tools:
        builder.add_node("tools", ToolNode(tools, handle_tool_errors=_tool_error_message))
        builder.add_conditional_edges("agent", tools_condition)  # routes to "tools" or END
        builder.add_edge("tools", "agent")  # loop back: the LLM sees every tool result
    else:
        builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer or MemorySaver())


async def build_agent(config_path: str | None = None):
    """Discover MCP tools (tools/list) and compile the graph. Returns (graph, server statuses)."""
    tools, statuses = await discover_tools(config_path or os.getenv("MCP_SERVERS_CONFIG", "mcp_config.json"))
    graph = build_graph(build_llm(), tools)
    return graph, statuses


async def _close_interrupted_turn(graph, config: dict, note: str) -> None:
    """Keep the saved history valid after a run stops mid-loop.

    If the run stopped right after the LLM requested tools, the history ends with
    unanswered tool calls, which the LLM API rejects on the next turn; those get a
    short error reply. Either way the turn is closed with a final AI message so the
    next turn (and "what did I ask last?") sees a complete exchange."""
    state = await graph.aget_state(config)
    messages = state.values.get("messages", [])
    if not messages or isinstance(messages[-1], HumanMessage):
        return  # failed before any tool work; history is already valid
    last = messages[-1]
    if isinstance(last, AIMessage) and not last.tool_calls:
        return  # turn already finished normally
    replies = []
    if isinstance(last, AIMessage):
        replies = [ToolMessage(content=note, tool_call_id=call["id"], status="error") for call in last.tool_calls]
    await graph.aupdate_state(config, {"messages": [*replies, AIMessage(content=note)]}, as_node="agent")


async def run_turn(graph, query: str, session_id: str) -> str:
    """Run one user turn in the session's thread and return the final answer text."""
    config = {"configurable": {"thread_id": session_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        result = await graph.ainvoke({"messages": [HumanMessage(content=query)]}, config)
    except GraphRecursionError:
        logger.warning("Recursion limit hit for session %s", session_id)
        await _close_interrupted_turn(graph, config, STOPPED_MESSAGE)
        return STOPPED_MESSAGE
    except Exception:
        await _close_interrupted_turn(graph, config, "This turn was interrupted by an error.")
        raise
    return result["messages"][-1].text or "I don't have a response for that."
