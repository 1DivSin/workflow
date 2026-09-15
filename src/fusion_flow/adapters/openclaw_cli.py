"""OpenClaw Agent Runtime backed by the host-owned CLI."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from typing import Mapping, Sequence

from ..agent_runtime import AgentRequest, AgentResult, parse_agent_result


_SAFE_AGENT_ID = re.compile(r"[^A-Za-z0-9_.-]+")


class OpenClawCliRuntime:
    """Run one Agent Step through ``openclaw agent --json``.

    OpenClaw owns Gateway authentication, pairing, and provider credentials.
    The workflow passes only a stable session key and a short-lived prompt file.
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

    def command_for(
        self,
        request: AgentRequest,
        *,
        message_file: str | None = None,
    ) -> tuple[str, ...]:
        if message_file is None:
            raise ValueError("OpenClaw message_file is required")
        args = [
            *self.command,
            "--session-key",
            self.session_key(request.session_id),
            "--message-file",
            message_file,
            "--json",
        ]
        if request.model:
            args.extend(("--model", request.model))
        if request.timeout_seconds is not None:
            args.extend(("--timeout", str(request.timeout_seconds)))
        return tuple(args)

    async def invoke(self, request: AgentRequest) -> AgentResult:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".fusion-flow-",
                suffix=".prompt",
                dir=request.workspace,
                delete=False,
            ) as prompt_file:
                prompt_file.write(request.prompt)
                message_file = prompt_file.name
        except OSError as error:
            return AgentResult(status="error", error=f"could not create OpenClaw prompt file: {error}")

        try:
            process = await asyncio.create_subprocess_exec(
                *self.command_for(request, message_file=message_file),
                cwd=str(request.workspace),
                env=self.env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            os.unlink(message_file)
            return AgentResult(status="error", error=f"could not start OpenClaw: {error}")

        try:
            communicate = process.communicate()
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
        finally:
            try:
                os.unlink(message_file)
            except FileNotFoundError:
                pass

        payload = self._parse_stdout(stdout)
        if payload is None:
            details = stderr.decode("utf-8", errors="replace").strip()
            details = details or f"OpenClaw returned invalid JSON (exit code {process.returncode})"
            return AgentResult(
                status="error",
                session_id=self.session_key(request.session_id),
                error=details,
            )

        result = parse_agent_result(self._normalize_payload(payload))
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
    def _normalize_payload(payload: Mapping[str, object]) -> dict[str, object]:
        nested = payload.get("result")
        if not isinstance(nested, Mapping):
            return dict(payload)
        out = dict(payload)
        text = nested.get("finalAssistantVisibleText") or nested.get("finalAssistantRawText")
        if not isinstance(text, str) or not text:
            for item in nested.get("payloads", []):
                if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                    text = item["text"]
                    break
        if isinstance(text, str) and text:
            out["final"] = text
        meta = nested.get("meta")
        if isinstance(meta, Mapping):
            usage = meta.get("usage")
            if not isinstance(usage, Mapping) and isinstance(meta.get("agentMeta"), Mapping):
                usage = meta["agentMeta"].get("usage")
            if isinstance(usage, Mapping):
                out["usage"] = dict(usage)
        return out

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
