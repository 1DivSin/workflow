from __future__ import annotations
import asyncio, json, os
from dataclasses import dataclass
from typing import Any

@dataclass
class OpenClawResult:
    text: str
    raw: dict[str, Any]

class OpenClawGatewayClient:
    """OpenClaw agent adapter using the official local agent CLI/gateway surface."""
    def __init__(self, command: tuple[str, ...] = ("openclaw", "agent", "--local", "--json"), *, cwd: str | None = None, env: dict[str, str] | None = None):
        self.command, self.cwd, self.env = command, cwd, env
    async def prompt(self, text: str, *, session_id: str | None = None) -> OpenClawResult:
        args = list(self.command)
        if session_id: args += ["--session-id", session_id]
        args += ["--message", text]
        proc = await asyncio.create_subprocess_exec(*args, cwd=self.cwd, env=self.env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0: raise RuntimeError(f"OpenClaw agent failed ({proc.returncode}): {stderr.decode(errors='replace')}")
        raw = json.loads(stdout.decode())
        text_out = raw.get("result", {}).get("text") or raw.get("text") or raw.get("response") or ""
        if not isinstance(text_out, str): raise RuntimeError("OpenClaw agent returned no text")
        return OpenClawResult(text_out, raw)
