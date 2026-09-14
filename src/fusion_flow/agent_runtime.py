"""Host-neutral contract for executing one workflow Agent Step."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping, Protocol


AgentStatus = Literal["ok", "error", "timeout", "waiting_for_user"]


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """Input sent from the workflow scheduler to one host executor."""

    prompt: str
    session_id: str
    workspace: Path
    model: str | None = None
    timeout_seconds: int | None = None

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("AgentRequest.prompt must not be empty")
        if not self.session_id.strip():
            raise ValueError("AgentRequest.session_id must not be empty")
        if self.timeout_seconds is not None and (
            type(self.timeout_seconds) is not int or self.timeout_seconds <= 0
        ):
            raise ValueError("AgentRequest.timeout_seconds must be a positive integer or None")


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Normalized result returned by a host executor."""

    status: AgentStatus
    text: str = ""
    session_id: str | None = None
    usage: Mapping[str, int] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class AgentRuntime(Protocol):
    """Execute Agent Steps without exposing a concrete host SDK."""

    def supports_executor(self, executor_kind: str) -> bool:
        ...

    async def invoke(self, request: AgentRequest) -> AgentResult:
        ...


def parse_agent_result(payload: Mapping[str, object]) -> AgentResult:
    """Normalize an executor JSON object into the workflow result contract."""

    raw_status = payload.get("status")
    if raw_status is None:
        raw_status = "ok" if payload.get("ok") is True else "error"
    status = raw_status if raw_status in {"ok", "error", "timeout", "waiting_for_user"} else "error"

    raw_text = payload.get("final", payload.get("text", ""))
    text = raw_text if isinstance(raw_text, str) else ""

    raw_session = payload.get("sessionId", payload.get("session_id", payload.get("session")))
    session_id = raw_session if isinstance(raw_session, str) else None

    raw_usage = payload.get("usage")
    usage: dict[str, int] = {}
    if isinstance(raw_usage, Mapping):
        for key, value in raw_usage.items():
            if isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                usage[key] = value

    raw_error = payload.get("error")
    if isinstance(raw_error, Mapping):
        raw_error = raw_error.get("message")
    error = raw_error if isinstance(raw_error, str) else None

    return AgentResult(
        status=status,
        text=text,
        session_id=session_id,
        usage=usage,
        error=error,
    )
