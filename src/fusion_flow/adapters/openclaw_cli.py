"""OpenClaw Agent Runtime backed by the host-owned CLI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import replace
from typing import Mapping, Sequence

from ..agent_runtime import AgentRequest, AgentResult, parse_agent_result


_SAFE_AGENT_ID = re.compile(r"[^A-Za-z0-9_.-]+")


class OpenClawCliRuntime:
    """Run one Agent Step through ``openclaw agent --json``.

    OpenClaw owns Gateway authentication, pairing, and provider credentials.
    The workflow passes only a stable session key and the prompt on stdin.
    """

    def __init__(
        self,
        command: Sequence[str] = ("openclaw", "agent"),
        *,
        agent_id: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if not command or any(not part for part in command):
            raise ValueError("OpenClaw command must contain at least one non-empty argument")
        self.command = tuple(command)
        self.agent_id = self._safe_agent_id(agent_id or os.environ.get("OPENCLAW_AGENT_ID", "main"))
        self.env = dict(env) if env is not None else None

    def supports_executor(self, executor_kind: str) -> bool:
        return executor_kind == "Agent"

    @staticmethod
    def _safe_agent_id(value: str) -> str:
        safe = _SAFE_AGENT_ID.sub("-", value.strip()).strip("-")
        return safe[:80] or "main"

    def session_key(self, session_id: str) -> str:
        digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return f"agent:{self.agent_id}:workflow:{digest}"

    def command_for(self, request: AgentRequest) -> tuple[str, ...]:
        args = [
            *self.command,
            "--session-key",
            self.session_key(request.session_id),
            "--message-file",
            "-",
            "--json",
        ]
        if request.model:
            args.extend(("--model", request.model))
        if request.timeout_seconds is not None:
            args.extend(("--timeout", str(request.timeout_seconds)))
        return tuple(args)

    async def invoke(self, request: AgentRequest) -> AgentResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command_for(request),
                cwd=str(request.workspace),
                env=self.env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            return AgentResult(status="error", error=f"could not start OpenClaw: {error}")

        try:
            communicate = process.communicate(request.prompt.encode("utf-8"))
            if request.timeout_seconds is None:
                stdout, stderr = await communicate
            else:
                stdout, stderr = await asyncio.wait_for(communicate, request.timeout_seconds + 5)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return AgentResult(
                status="timeout",
                session_id=self.session_key(request.session_id),
                error=f"OpenClaw agent exceeded {request.timeout_seconds}s",
            )

        payload = self._parse_stdout(stdout)
        if payload is None:
            details = stderr.decode("utf-8", errors="replace").strip()
            details = details or f"OpenClaw returned invalid JSON (exit code {process.returncode})"
            return AgentResult(
                status="error",
                session_id=self.session_key(request.session_id),
                error=details,
            )

        result = parse_agent_result(payload)
        if process.returncode and result.error is None:
            result = replace(
                result,
                status="error" if result.status == "ok" else result.status,
                error=stderr.decode("utf-8", errors="replace").strip()
                or f"OpenClaw exited with code {process.returncode}",
            )
        if result.session_id is None:
            result = replace(result, session_id=self.session_key(request.session_id))
        return result

    @staticmethod
    def _parse_stdout(stdout: bytes) -> dict[str, object] | None:
        text = stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        candidates = [text, *reversed(text.splitlines())]
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return None
