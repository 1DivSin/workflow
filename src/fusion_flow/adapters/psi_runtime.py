"""Optional PSI session bindings kept outside the host-neutral workflow core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


try:  # pragma: no cover - exercised only when psi-agent is installed
    from psi_agent.session.agent import AgentError, SessionAgent, current_tool_ai_socket
    from psi_agent.session.ai_client import AiClient
    from psi_agent.session.conversation import Conversation
    from psi_agent.session.schedule_registry import ScheduleRegistry
    from psi_agent.session.tool_registry import FileEntry, ToolFunction, ToolRegistry
except ImportError:  # pragma: no cover - covered by standalone host checks
    AgentError = RuntimeError

    class SessionAgent:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("No host Agent Runtime is installed")

    class AiClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("No host Agent Runtime is installed")

    class Conversation:
        def __init__(self, *, messages: list[dict[str, Any]] | None = None, **_kwargs: object) -> None:
            self.messages = list(messages or [])

    class ScheduleRegistry:
        async def refresh(self) -> dict[str, str]:
            return {}

    @dataclass
    class ToolFunction:
        name: str
        description: str
        parameters: dict[str, Any]

        @classmethod
        def from_callable(cls, function: Any) -> "ToolFunction":
            return cls(function.__name__, function.__doc__ or "", {"type": "object"})

    @dataclass
    class FileEntry:
        file_hash: str
        tools: dict[str, ToolFunction]
        funcs: dict[str, Any]

    class ToolRegistry:
        def __init__(
            self,
            *,
            files: dict[str, FileEntry] | None = None,
            **_kwargs: object,
        ) -> None:
            self._files = dict(files or {})

        @property
        def tools(self) -> dict[str, ToolFunction]:
            result: dict[str, ToolFunction] = {}
            for entry in self._files.values():
                result.update(entry.tools)
            return result

        def get(self, name: str) -> Any:
            for entry in self._files.values():
                if name in entry.funcs:
                    return entry.funcs[name]
            return None

        @classmethod
        async def load(cls, *_args: object, **_kwargs: object) -> "ToolRegistry":
            return cls()

        async def refresh(self) -> dict[str, str]:
            return {}

    def current_tool_ai_socket() -> str | None:
        return None


__all__ = [
    "AgentError",
    "AiClient",
    "Conversation",
    "FileEntry",
    "ScheduleRegistry",
    "SessionAgent",
    "ToolFunction",
    "ToolRegistry",
    "current_tool_ai_socket",
]
