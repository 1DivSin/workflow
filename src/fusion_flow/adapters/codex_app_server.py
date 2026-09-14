from __future__ import annotations
import asyncio, json
from dataclasses import dataclass
from typing import Any, AsyncIterator

@dataclass
class CodexEvent:
    method: str
    params: dict[str, Any]

class CodexAppServerClient:
    """Codex app-server JSONL client (stdio transport)."""
    def __init__(self, command: tuple[str, ...] = ("codex", "app-server", "--stdio"), *, cwd: str | None = None, env: dict[str, str] | None = None):
        self.command, self.cwd, self.env = command, cwd, env
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 0

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(*self.command, cwd=self.cwd, env=self.env, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await self.request("initialize", {"clientInfo": {"name": "fusion-flow", "version": "0.1"}, "capabilities": {}})

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None: raise RuntimeError("Codex app-server is not started")
        self._next_id += 1; ident = self._next_id
        msg = {"id": ident, "method": method};
        if params is not None: msg["params"] = params
        self.proc.stdin.write((json.dumps(msg) + "\n").encode()); await self.proc.stdin.drain()
        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("Codex app-server closed stdout")
            data = json.loads(line)
            if data.get("id") == ident:
                if "error" in data: raise RuntimeError(f"Codex {method} failed: {data['error']}")
                return data.get("result", {})

    async def prompt(self, cwd: str, text: str) -> AsyncIterator[CodexEvent]:
        thread = await self.request("thread/start", {"cwd": cwd})
        thread_id = thread.get("thread", {}).get("id") or thread.get("threadId")
        if not isinstance(thread_id, str): raise RuntimeError("Codex thread/start returned no thread id")
        if self.proc is None or self.proc.stdin is None or self.proc.stdout is None: raise RuntimeError("Codex app-server is not started")
        self._next_id += 1; ident = self._next_id
        self.proc.stdin.write((json.dumps({"id": ident, "method": "turn/start", "params": {"threadId": thread_id, "input": [{"type": "text", "text": text}]}}) + "\n").encode()); await self.proc.stdin.drain()
        acknowledged = False
        while True:
            line = await self.proc.stdout.readline()
            if not line: raise RuntimeError("Codex app-server closed stdout")
            data = json.loads(line)
            method = data.get("method")
            if isinstance(method, str):
                params = data.get("params", {})
                log_path = self.env.get("CODEX_EVENT_LOG") if self.env else None
                if log_path:
                    with open(log_path, "a", encoding="utf-8") as log:
                        log.write(json.dumps({
                            "method": method,
                            "param_keys": sorted(params.keys()) if isinstance(params, dict) else [],
                            "delta": params.get("delta") if isinstance(params, dict) and method == "item/agentMessage/delta" else None,
                        }, ensure_ascii=False) + "\n")
                yield CodexEvent(method, params)
                if method in {"turn/completed", "turn/failed", "turn/cancelled"}:
                    return
            if data.get("id") == ident:
                acknowledged = True
            if acknowledged and data.get("method") == "turn/completed":
                return

    async def close(self) -> None:
        if self.proc is None: return
        if self.proc.stdin: self.proc.stdin.close()
        await self.proc.wait(); self.proc = None
