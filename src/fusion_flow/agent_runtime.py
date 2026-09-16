"""Minimal host boundary for one workflow Agent Step."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

@dataclass(frozen=True, slots=True)
class AgentInvocation:
    prompt: str
    session_id: str
    workspace: Path
    model: str | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip() or not self.session_id.strip():
            raise ValueError("AgentInvocation prompt and session_id must be non-empty")

@dataclass(frozen=True, slots=True)
class AgentReply:
    text: str = ""
    status: str = "ok"
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

class AgentRuntime(Protocol):
    def supports_agent_steps(self) -> bool: ...
    async def run_agent(self, invocation: AgentInvocation) -> AgentReply: ...
