"""Optional PSI bindings; the workflow runner stays host-neutral."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

try:
    from psi_agent.session.agent import AgentError, SessionAgent, current_tool_ai_socket
    from psi_agent.session.ai_client import AiClient
    from psi_agent.session.conversation import Conversation
    from psi_agent.session.schedule_registry import ScheduleRegistry
    from psi_agent.session.tool_registry import FileEntry, ToolFunction, ToolRegistry
except ImportError:  # pragma: no cover
    AgentError = RuntimeError
    class SessionAgent:
        def __init__(self, *_args: object, **_kwargs: object) -> None: raise RuntimeError("PSI runtime unavailable")
    class AiClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None: raise RuntimeError("PSI runtime unavailable")
    class Conversation:
        def __init__(self, *, messages=None, **_kwargs: object) -> None: self.messages = list(messages or [])
    class ScheduleRegistry:
        async def refresh(self) -> dict[str, str]: return {}
    @dataclass
    class ToolFunction:
        name: str
        description: str = ""
        parameters: dict[str, Any] | None = None
        @classmethod
        def from_callable(cls, function: Any) -> "ToolFunction": return cls(function.__name__, function.__doc__ or "", {"type": "object"})
    @dataclass
    class FileEntry:
        file_hash: str
        tools: dict[str, ToolFunction]
        funcs: dict[str, Any]
    class ToolRegistry:
        def __init__(self, *, files=None, **_kwargs: object) -> None: self.files = dict(files or {})
        @property
        def tools(self) -> dict[str, ToolFunction]:
            result = {}
            for entry in self.files.values(): result.update(entry.tools)
            return result
        def get(self, name: str) -> Any:
            for entry in self.files.values():
                if name in entry.funcs: return entry.funcs[name]
            return None
        @classmethod
        async def load(cls, *_args: object, **_kwargs: object) -> "ToolRegistry": return cls()
        async def refresh(self) -> dict[str, str]: return {}
    def current_tool_ai_socket() -> str | None: return None
