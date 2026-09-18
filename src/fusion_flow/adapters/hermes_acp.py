from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any, AsyncIterator

from ..process import close_subprocess, create_subprocess_exec, drain_stream


@dataclass
class ACPEvent:
    method: str
    params: dict[str, Any]


class HermesACPClient:
    """Minimal Hermes ACP stdio JSON-RPC client.

    Hermes keeps JSON-RPC on stdout and diagnostics on stderr. This client owns
    the subprocess and never imports psi_agent.
    """

    def __init__(
        self,
        command: tuple[str, ...] = ("hermes-acp",),
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command, self.cwd, self.env = command, cwd, env
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._stderr_task: asyncio.Task[bytes] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}

    async def start(self) -> None:
        if self.proc is not None:
            return
        env = dict(os.environ)
        env.update(self.env or {})
        env_file = Path(env.get("HOME", str(Path.home()))) / ".hermes" / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env.setdefault(k.strip(), v.strip().strip('"'))
        try:
            self.proc = await create_subprocess_exec(
                *self.command,
                cwd=self.cwd,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise RuntimeError(f"Hermes ACP could not start: {error}") from error
        self._stderr_task = asyncio.create_task(drain_stream(self.proc.stderr))
        try:
            await self.request(
                "initialize",
                {"protocolVersion": 1, "clientInfo": {"name": "fusion-flow", "version": "0.1"}},
            )
        except BaseException:
            await self.close()
            raise

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Hermes ACP client is not started")
        self._next_id += 1
        ident = self._next_id
        payload = {"jsonrpc": "2.0", "id": ident, "method": method}
        if params is not None:
            payload["params"] = params
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Hermes ACP server closed stdout")
            msg = json.loads(line)
            if msg.get("id") == ident:
                if "error" in msg:
                    raise RuntimeError(f"Hermes ACP {method} failed: {msg['error']}")
                return msg.get("result", {})

    async def new_session(self, cwd: str) -> str:
        result = await self.request("session/new", {"cwd": cwd, "mcpServers": []})
        session_id = result.get("sessionId")
        if not isinstance(session_id, str):
            raise RuntimeError("Hermes ACP session/new returned no sessionId")
        return session_id

    async def prompt(self, session_id: str, text: str) -> AsyncIterator[ACPEvent]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Hermes ACP client is not started")
        self._next_id += 1
        ident = self._next_id
        payload = {
            "jsonrpc": "2.0",
            "id": ident,
            "method": "session/prompt",
            "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]},
        }
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Hermes ACP server closed stdout")
            msg = json.loads(line)
            if msg.get("method") == "session/update":
                yield ACPEvent(msg["method"], msg.get("params", {}))
            elif msg.get("id") == ident:
                if "error" in msg:
                    raise RuntimeError(f"Hermes ACP session/prompt failed: {msg['error']}")
                return

    async def cancel(self, session_id: str) -> None:
        await self.request("session/cancel", {"sessionId": session_id})

    async def close(self) -> None:
        process = self.proc
        if process is None:
            return
        try:
            await close_subprocess(process, self._stderr_task)
        finally:
            self.proc = None
            self._stderr_task = None
