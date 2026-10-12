"""A deliberately broken MCP server used to test failure handling over a real stdio transport.

It speaks just enough JSON-RPC 2.0 to pass `initialize` and `tools/list`, then misbehaves on
`tools/call` depending on the tool name:
  bad_shape -> result does not match the CallToolResult schema (malformed response)
  audio     -> valid MCP, but a content type the agent cannot read
  crash     -> the process exits mid-call (transport closes)

Run with --garbage to print non-JSON output and exit before the handshake.
"""

import json
import sys

TOOLS = [
    {"name": name, "description": f"Test tool '{name}'.", "inputSchema": {"type": "object", "properties": {}}}
    for name in ("bad_shape", "audio", "crash")
]


def reply(request_id, result) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}) + "\n")
    sys.stdout.flush()


def handle_call(request_id, tool: str) -> None:
    if tool == "bad_shape":
        reply(request_id, {"content": "this should be a list of content blocks"})
    elif tool == "audio":
        reply(request_id, {"content": [{"type": "audio", "data": "AAAA", "mimeType": "audio/wav"}]})
    elif tool == "crash":
        sys.exit(1)


def main() -> None:
    if "--garbage" in sys.argv:
        sys.stdout.write("this is not json-rpc\n")
        sys.stdout.flush()
        return
    for line in sys.stdin:
        message = json.loads(line)
        method, request_id = message.get("method"), message.get("id")
        if method == "initialize":
            reply(request_id, {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "broken-test-server", "version": "0.0.1"},
            })
        elif method == "tools/list":
            reply(request_id, {"tools": TOOLS})
        elif method == "tools/call":
            handle_call(request_id, message["params"]["name"])


if __name__ == "__main__":
    main()
