"""Small stdio MCP bridge for the three public workflow tools.

The bridge intentionally uses only the standard library.  Hosts can run it as
``python -m fusion_flow.mcp_server`` and register the process as an MCP server.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from typing import Any, Awaitable, Callable


async def run_flow(**arguments: Any) -> str:
    from run_flow import run_flow as implementation

    return await implementation(**arguments)


async def run_flow_resume(**arguments: Any) -> str:
    from run_flow import run_flow_resume as implementation

    return await implementation(**arguments)


async def flow_manage(**arguments: Any) -> str:
    from flow_manage import flow_manage as implementation

    return await implementation(**arguments)


_TOOLS: dict[str, tuple[Callable[..., Awaitable[str]], dict[str, Any]]] = {
    "run_flow": (
        run_flow,
        {
            "type": "object",
            "properties": {
                "flow_path": {"type": "string"},
                "inputs_json": {"type": "string", "default": "{}"},
                "resource_capacities_json": {"type": "string", "default": ""},
                "max_loop_epochs": {"type": "integer", "minimum": 1, "default": 100},
            },
            "required": ["flow_path"],
        },
    ),
    "run_flow_resume": (
        run_flow_resume,
        {
            "type": "object",
            "properties": {
                "run_id": {"type": "string"},
                "request_id": {"type": "string"},
                "human_response_json": {"type": "string"},
            },
            "required": ["run_id", "request_id", "human_response_json"],
        },
    ),
    "flow_manage": (
        flow_manage,
        {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "view", "create", "patch", "promote"]},
                "flow_name": {"type": "string"},
                "description": {"type": "string"},
                "category": {"type": "string"},
                "body": {"type": "string"},
                "flow_ts": {"type": "string"},
                "target": {"type": "string"},
                "flow_source": {"type": "string"},
            },
        },
    ),
}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


async def dispatch(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dynamic-workflow", "version": "0.1.0"},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {"name": name, "description": f"Dynamic Workflow {name}", "inputSchema": schema}
                    for name, (_handler, schema) in _TOOLS.items()
                ]
            },
        }
    if method != "tools/call":
        return _error(request_id, -32601, f"Method not found: {method}")
    params = request.get("params")
    if not isinstance(params, dict) or not isinstance(params.get("name"), str):
        return _error(request_id, -32602, "tools/call requires params.name")
    tool = _TOOLS.get(params["name"])
    if tool is None:
        return _error(request_id, -32602, f"Unknown tool: {params['name']}")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "params.arguments must be an object")
    # Resolve from globals so embedders can replace a handler (and tests can
    # inject a host-specific runtime) without rebuilding the registry.
    handler = globals()[params["name"]]
    try:
        result = handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": str(result)}]}}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": request_id, "result": {"isError": True, "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}]}}


async def serve_stdio() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as error:
            response = _error(None, -32700, f"Invalid JSON: {error.msg}")
        else:
            if not isinstance(request, dict):
                response = _error(None, -32600, "JSON-RPC request must be an object")
            else:
                try:
                    response = await dispatch(request)
                except Exception as error:
                    response = _error(request.get("id"), -32603, f"Internal error: {type(error).__name__}: {error}")
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def main() -> None:
    asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()
