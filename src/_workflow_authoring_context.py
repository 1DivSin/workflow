"""Standalone fallback for the optional psi-agent authoring context."""
from contextvars import ContextVar

_prompt: ContextVar[str | None] = ContextVar("workflow_authoring_prompt", default=None)

def current_prompt() -> str | None:
    return _prompt.get()
