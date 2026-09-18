"""OpenClaw CLI adapter owned by the host process."""

from __future__ import annotations
import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence
from ..agent_runtime import AgentInvocation, AgentReply
from ..process import close_subprocess, create_subprocess_exec


_HUMAN_SESSION_PREFIX = "human-"


class OpenClawCliRuntime:
    def __init__(
        self,
        command: Sequence[str] = ("openclaw", "agent"),
        *,
        env: Mapping[str, str] | None = None,
    ):
        if not command or any(not item for item in command):
            raise ValueError("OpenClaw command must not be empty")
        self.command = tuple(command)
        self.env = dict(env) if env is not None else None
        self.agent_id = os.getenv("OPENCLAW_AGENT_ID", "main")

    def supports_agent_steps(self) -> bool:
        return True

    def _key(self, session_id: str) -> str:
        return (
            f"agent:{self.agent_id}:workflow:{hashlib.sha256(session_id.encode()).hexdigest()[:32]}"
        )

    def _ambient_config(self) -> Path:
        env = self.env if self.env is not None else os.environ
        explicit = env.get("OPENCLAW_CONFIG_PATH", "").strip()
        if explicit:
            return Path(explicit).expanduser()
        state = env.get("OPENCLAW_STATE_DIR", "").strip() or env.get("OPENCLAW_HOME", "").strip()
        return (
            Path(state).expanduser() / "openclaw.json"
            if state
            else Path.home() / ".openclaw" / "openclaw.json"
        )

    def _safe_human_exec(
        self, invocation: AgentInvocation, directory: Path
    ) -> tuple[tuple[str, ...], dict[str, str]]:
        """Build an isolated OpenClaw exec turn restricted to workspace reads."""
        env = dict(self.env) if self.env is not None else dict(os.environ)
        ambient = self._ambient_config()
        # Explicitly expose only `read` and force filesystem tools to remain
        # inside the workspace selected by --cwd.
        config: dict[str, object] = {
            "tools": {
                "profile": "coding",
                "allow": ["read"],
                "fs": {"workspaceOnly": True},
            }
        }
        if ambient.is_file():
            config["$include"] = str(ambient.resolve())
            roots = [
                part for part in env.get("OPENCLAW_INCLUDE_ROOTS", "").split(os.pathsep) if part
            ]
            parent = str(ambient.resolve().parent)
            if parent not in roots:
                roots.append(parent)
            env["OPENCLAW_INCLUDE_ROOTS"] = os.pathsep.join(roots)
        config_path = directory / "openclaw-human.json"
        config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        args = (
            *self.command,
            "exec",
            "--config",
            str(config_path),
            "--cwd",
            str(invocation.workspace),
            "--message-file",
            "-",
            "--json",
        )
        if invocation.model:
            args += ("--model", invocation.model)
        return args, env

    async def run_agent(self, invocation: AgentInvocation) -> AgentReply:
        temporary: tempfile.TemporaryDirectory[str] | None = None
        if invocation.session_id.startswith(_HUMAN_SESSION_PREFIX):
            temporary = tempfile.TemporaryDirectory(prefix="workflow-human-")
            args, child_env = self._safe_human_exec(invocation, Path(temporary.name))
        else:
            args = (
                *self.command,
                "--session-key",
                self._key(invocation.session_id),
                "--message-file",
                "-",
                "--json",
            )
            if invocation.model:
                args += ("--model", invocation.model)
            child_env = self.env
        process = None
        try:
            process = await create_subprocess_exec(
                *args,
                cwd=str(invocation.workspace),
                env=child_env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(invocation.prompt.encode())
        except OSError as error:
            return AgentReply(status="error", error=f"could not start OpenClaw: {error}")
        finally:
            try:
                if process is not None and process.returncode is None:
                    await close_subprocess(process)
            finally:
                if temporary is not None:
                    temporary.cleanup()
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return AgentReply(
                status="error",
                error=stderr.decode("utf-8", "replace") or "OpenClaw returned invalid JSON",
            )
        if not isinstance(payload, dict):
            return AgentReply(status="error", error="OpenClaw result must be an object")
        status = payload.get("status", "ok" if payload.get("ok") is True else "error")
        text = payload.get("final")
        if not isinstance(text, str):
            text = payload.get("text")
        nested = payload.get("result")
        if not isinstance(text, str) and isinstance(nested, dict):
            text = nested.get("finalAssistantVisibleText")
            if not isinstance(text, str):
                text = nested.get("text")
        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("message")
        reply = AgentReply(
            text=text if isinstance(text, str) else "",
            status=status if isinstance(status, str) else "error",
            error=error if isinstance(error, str) else None,
        )
        if process.returncode and reply.error is None:
            return replace(
                reply,
                status="error",
                error=stderr.decode("utf-8", "replace")
                or f"OpenClaw exited with {process.returncode}",
            )
        return reply
