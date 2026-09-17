"""Subprocess boundary for the native OpenClaw workflow plugin."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Awaitable, Callable

from flow_manage import flow_manage
import run_flow as run_flow_module


_PREFIX = "__FUSION_FLOW_BRIDGE__"


def _emit(payload: dict[str, object]) -> None:
    print(_PREFIX + json.dumps(payload, ensure_ascii=False, allow_nan=False))


def _preflight_runtime(name: str) -> None:
    """Turn run_flow's legacy host-error JSON into a real bridge failure.

    Once this check succeeds, an output artifact legitimately named ``error`` is
    ordinary workflow data and must not be interpreted by the transport layer.
    """
    if name not in {"run_flow", "run_flow_resume"}:
        return
    agent_runtime = run_flow_module._host_agent_runtime()
    ai_socket = run_flow_module._host_ai_socket(run_flow_module.current_tool_ai_socket)
    if (
        not run_flow_module._host_available(run_flow_module._WORKSPACE_DIR)
        and ai_socket is None
        and agent_runtime is None
    ):
        raise RuntimeError("No supported host runtime detected")
    if ai_socket is None and agent_runtime is None:
        raise RuntimeError("No runtime adapter is registered for the detected host")


async def _invoke(name: str, params: dict[str, object]) -> object:
    functions: dict[str, Callable[..., Awaitable[Any]]] = {
        "run_flow": run_flow_module.run_flow,
        "run_flow_resume": run_flow_module.run_flow_resume,
        "flow_manage": flow_manage,
    }
    try:
        function = functions[name]
    except KeyError as error:
        raise ValueError(f"Unsupported workflow bridge function: {name}") from error
    _preflight_runtime(name)
    return await function(**params)


def main() -> int:
    if len(sys.argv) != 2:
        _emit({"ok": False, "error": "bridge requires exactly one function name"})
        return 2
    try:
        params = json.load(sys.stdin)
        if not isinstance(params, dict):
            raise ValueError("bridge arguments must be a JSON object")
        result = asyncio.run(_invoke(sys.argv[1], params))
        _emit({"ok": True, "result": result})
        return 0
    except Exception as error:
        _emit({"ok": False, "error": f"{type(error).__name__}: {error}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
