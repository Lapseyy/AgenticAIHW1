"""HTTP entrypoint for the agent.

POST /chat   {"query": str, "session_id": str} -> {"response": str}
GET  /health MCP server status and discovered tools

Cloud Run injects PORT at runtime; the server binds 0.0.0.0:$PORT (default 8080).
"""

import logging
import os
from contextlib import asynccontextmanager

import openai
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

load_dotenv()  # local development only; Cloud Run gets env vars from --set-env-vars

from agent import build_agent, run_turn  # noqa: E402  (needs env loaded first)
from mcp_client import status_report  # noqa: E402

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    session_id: str = Field(min_length=1, max_length=128)


class ChatResponse(BaseModel):
    response: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent, app.state.mcp_status = await build_agent()
    loaded = [status.name for status in app.state.mcp_status if status.ok]
    logger.info("Agent ready. MCP servers loaded: %s", loaded or "none")
    yield


app = FastAPI(title="CSCI 599 A1 MCP Agent", lifespan=lifespan)


@app.get("/health")
async def health(request: Request) -> dict:
    return {"status": "ok", "mcp_servers": status_report(request.app.state.mcp_status)}


def _error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"response": message})


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    try:
        answer = await run_turn(request.app.state.agent, body.query, body.session_id)
    except openai.RateLimitError:
        logger.warning("LLM rate limit hit")
        return _error(503, "The language model is rate-limited right now. Please try again in a minute.")
    except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError):
        logger.exception("LLM backend unreachable")
        return _error(503, "The language model backend is unreachable right now. Please try again.")
    except openai.APIError:
        logger.exception("LLM backend rejected the request")
        return _error(502, "The language model backend returned an error for this request.")
    except Exception:
        logger.exception("Unhandled error in /chat")
        return _error(500, "Sorry, something went wrong while processing your request.")
    return ChatResponse(response=answer)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
