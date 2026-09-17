"""Stable subprocess bridge used by native host plugins."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Awaitable, Callable


async def _invoke(action: str, params: dict[str, Any]) -> Any:
    from flow_manage import flow_manage
    from run_flow import run_flow, run_flow_resume

    functions: dict[str, Callable[..., Awaitable[Any]]] = {
        "run_flow": run_flow,
        "run_flow_resume": run_flow_resume,
        "flow_manage": flow_manage,
    }
    return await functions[action](**params)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dynamic-workflow-tool")
    parser.add_argument("action", choices=("run_flow", "run_flow_resume", "flow_manage"))
    args = parser.parse_args(argv)

    try:
        params = json.load(sys.stdin)
        if not isinstance(params, dict):
            raise ValueError("tool parameters must be a JSON object")
        result = asyncio.run(_invoke(args.action, params))
        envelope = {"ok": True, "result": result}
    except Exception as error:
        envelope = {"ok": False, "error": f"{type(error).__name__}: {error}"}

    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
