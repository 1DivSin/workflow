"""Host callback for OpenClaw in-process workflow plugins.

The OpenClaw plugin owns Gateway authentication and sub-agent lifecycle.  The
workflow core only depends on this narrow callback, so no WebSocket pairing or
psi-agent objects leak into the scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Protocol


@dataclass(frozen=True)
class OpenClawPluginRequest:
    prompt: str
    session_key: str
    tools: Mapping[str, object]


class OpenClawPluginRuntime(Protocol):
    async def run_agent(self, request: OpenClawPluginRequest) -> str: ...


class CallbackOpenClawRuntime:
    """Adapter used by an OpenClaw plugin callback (agent/run + wait + read)."""

    def __init__(self, callback: Callable[[OpenClawPluginRequest], Awaitable[str]]) -> None:
        self._callback = callback

    async def run_agent(self, request: OpenClawPluginRequest) -> str:
        result = await self._callback(request)
        if not isinstance(result, str):
            raise TypeError("OpenClaw plugin runtime must return text")
        return result

