from __future__ import annotations
import asyncio, json, os
from dataclasses import dataclass
from typing import Any, AsyncIterator

@dataclass
class ACPEvent:
    method: str
    params: dict[str, Any]

class HermesACPClient:
    """Minimal Hermes ACP stdio JSON-RPC client.

    Hermes keeps JSON-RPC on stdout and diagnostics on stderr. This client owns
    the subprocess and never imports psi_agent.
    """
    def __init__(self, command: tuple[str, ...] = ("hermes-acp",), *, cwd: str | None = None, env: dict[str, str] | None = None):
        self.command, self.cwd, self.env = command, cwd, env
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}

    async def start(self) -> None:
        if self.proc is not None:
            return
        self.proc = await asyncio.create_subprocess_exec(*self.command, cwd=self.cwd, env=self.env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self.request("initialize", {"protocolVersion": 1, "clientInfo": {"name": "fusion-flow", "version": "0.1"}})

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Hermes ACP client is not started")
        self._next_id += 1
        ident = self._next_id
        payload = {"jsonrpc": "2.0", "id": ident, "method": method}
        if params is not None: payload["params"] = params
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode())
        await self.proc.stdin.drain()
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                raise RuntimeError("Hermes ACP server closed stdout")
            msg = json.loads(line)
            if msg.get("id") == ident:
                if "error" in msg: raise RuntimeError(f"Hermes ACP {method} failed: {msg['error']}")
                return msg.get("result", {})

    async def new_session(self, cwd: str) -> str:
        result = await self.request("session/new", {"cwd": cwd})
        session_id = result.get("sessionId")
        if not isinstance(session_id, str): raise RuntimeError("Hermes ACP session/new returned no sessionId")
        return session_id

    async def prompt(self, session_id: str, text: str) -> AsyncIterator[ACPEvent]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("Hermes ACP client is not started")
        self._next_id += 1
        ident = self._next_id
        payload = {"jsonrpc": "2.0", "id": ident, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]}}
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode()); await self.proc.stdin.drain()
        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("Hermes ACP server closed stdout")
            msg = json.loads(line)
            if msg.get("method") == "session/update":
                yield ACPEvent(msg["method"], msg.get("params", {}))
            elif msg.get("id") == ident:
                if "error" in msg: raise RuntimeError(f"Hermes ACP session/prompt failed: {msg['error']}")
                return

    async def cancel(self, session_id: str) -> None:
        await self.request("session/cancel", {"sessionId": session_id})

    async def close(self) -> None:
        if self.proc is None: return
        if self.proc.stdin: self.proc.stdin.close()
        await self.proc.wait(); self.proc = None
