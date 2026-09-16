"""OpenClaw CLI adapter owned by the host process."""
from __future__ import annotations
import asyncio, hashlib, json, os
from dataclasses import replace
from typing import Mapping, Sequence
from ..agent_runtime import AgentInvocation, AgentReply

class OpenClawCliRuntime:
    def __init__(self, command: Sequence[str] = ("openclaw", "agent"), *, env: Mapping[str, str] | None = None):
        if not command or any(not item for item in command): raise ValueError("OpenClaw command must not be empty")
        self.command = tuple(command)
        self.env = dict(env) if env is not None else None
        self.agent_id = os.getenv("OPENCLAW_AGENT_ID", "main")

    def supports_agent_steps(self) -> bool: return True

    def _key(self, session_id: str) -> str:
        return f"agent:{self.agent_id}:workflow:{hashlib.sha256(session_id.encode()).hexdigest()[:32]}"

    async def run_agent(self, invocation: AgentInvocation) -> AgentReply:
        args = (*self.command, "--session-key", self._key(invocation.session_id), "--message-file", "-", "--json")
        if invocation.model: args += ("--model", invocation.model)
        try:
            process = await asyncio.create_subprocess_exec(*args, cwd=str(invocation.workspace), env=self.env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate(invocation.prompt.encode())
        except OSError as error:
            return AgentReply(status="error", error=f"could not start OpenClaw: {error}")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return AgentReply(status="error", error=stderr.decode("utf-8", "replace") or "OpenClaw returned invalid JSON")
        if not isinstance(payload, dict): return AgentReply(status="error", error="OpenClaw result must be an object")
        status = payload.get("status", "ok" if payload.get("ok") is True else "error")
        text = payload.get("final", payload.get("text", ""))
        error = payload.get("error")
        if isinstance(error, dict): error = error.get("message")
        reply = AgentReply(text=text if isinstance(text, str) else "", status=status if isinstance(status, str) else "error", error=error if isinstance(error, str) else None)
        if process.returncode and reply.error is None: return replace(reply, status="error", error=stderr.decode("utf-8", "replace") or f"OpenClaw exited with {process.returncode}")
        return reply
