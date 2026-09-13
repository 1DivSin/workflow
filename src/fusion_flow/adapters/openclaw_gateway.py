from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any

import websockets


@dataclass
class OpenClawResult:
    text: str
    raw: dict[str, Any]


class OpenClawGatewayClient:
    """OpenClaw gateway WebSocket RPC client."""

    def __init__(self, url: str = "ws://127.0.0.1:18789", *, token: str | None = None,
                 session_key: str = "agent:main:workflow") -> None:
        self.url, self.token, self.session_key = url, token or os.getenv("OPENCLAW_GATEWAY_TOKEN"), session_key
        self.ws: Any = None
        self._next_id = 0

    async def start(self) -> dict[str, Any]:
        self.ws = await websockets.connect(self.url, max_size=None)
        challenge = json.loads(await self.ws.recv())
        if challenge.get("event") != "connect.challenge":
            raise RuntimeError(f"OpenClaw gateway expected challenge, got {challenge!r}")
        params: dict[str, Any] = {
            "minProtocol": 4, "maxProtocol": 4,
            "client": {"id": "cli", "version": "workflow", "platform": "linux", "mode": "operator"},
            "role": "operator", "scopes": ["operator.read", "operator.write"],
            "caps": [], "commands": [], "permissions": {},
        }
        if self.token:
            params["auth"] = {"token": self.token}
        return await self.request("connect", params, request_id="connect")

    async def request(self, method: str, params: dict[str, Any] | None = None, *, request_id: str | None = None) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("OpenClaw gateway is not started")
        self._next_id += 1
        ident = request_id or f"workflow-{self._next_id}"
        await self.ws.send(json.dumps({"type": "req", "id": ident, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("type") == "event":
                continue
            if msg.get("id") != ident:
                continue
            if not msg.get("ok"):
                raise RuntimeError(f"OpenClaw {method} failed: {msg.get('error')}")
            return msg.get("payload", {})

    async def prompt(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        key = session_key or self.session_key
        accepted = await self.request("chat.send", {"sessionKey": key, "message": text, "deliver": False, "idempotencyKey": str(uuid.uuid4())})
        run_id = accepted.get("runId")
        if not isinstance(run_id, str):
            raise RuntimeError(f"OpenClaw chat.send returned no runId: {accepted!r}")
        result = await self.request("agent.wait", {"runId": run_id, "timeoutMs": 120000})
        text_out = result.get("text") or result.get("response") or result.get("message") or ""
        if not isinstance(text_out, str):
            raise RuntimeError(f"OpenClaw agent.wait returned no text: {result!r}")
        return OpenClawResult(text_out, result)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
