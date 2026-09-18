from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

import websockets
from websockets.exceptions import WebSocketException


@dataclass
class OpenClawResult:
    text: str
    payload: dict[str, Any]


@dataclass
class OpenClawEvent:
    event: str
    payload: dict[str, Any]


class OpenClawGatewayClient:
    """OpenClaw gateway WebSocket RPC client."""

    def __init__(self, url: str = "ws://127.0.0.1:18789", *, token: str | None = None,
                 session_key: str = "agent:main:workflow", timeout_seconds: float = 30.0) -> None:
        self.url, self.token, self.session_key = url, token or os.getenv("OPENCLAW_GATEWAY_TOKEN"), session_key
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.ws: Any = None
        self._next_id = 0

    async def start(self) -> dict[str, Any]:
        try:
            self.ws = await websockets.connect(self.url, max_size=None, open_timeout=self.timeout_seconds)
            challenge = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=self.timeout_seconds))
        except (OSError, WebSocketException, asyncio.TimeoutError, json.JSONDecodeError) as error:
            await self.close()
            raise RuntimeError(f"OpenClaw gateway connection failed: {error}") from error
        if not isinstance(challenge, dict) or challenge.get("event") != "connect.challenge":
            raise RuntimeError(f"OpenClaw gateway expected challenge, got {challenge!r}")
        params: dict[str, Any] = {
            "minProtocol": 4, "maxProtocol": 4,
            "client": {"id": "cli", "version": "workflow", "platform": sys.platform, "mode": "cli"},
            "role": "operator", "scopes": ["operator.read", "operator.write"],
            "caps": [], "commands": [], "permissions": {},
        }
        if self.token:
            params["auth"] = {"token": self.token}
        return await self.request("connect", params, request_id="connect")

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        response_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("OpenClaw gateway is not started")
        self._next_id += 1
        ident = request_id or f"workflow-{self._next_id}"
        timeout = self.timeout_seconds if response_timeout_seconds is None else response_timeout_seconds
        await self.ws.send(json.dumps({"type": "req", "id": ident, "method": method, "params": params or {}}))
        while True:
            try:
                msg = json.loads(await asyncio.wait_for(self.ws.recv(), timeout=timeout))
            except (WebSocketException, asyncio.TimeoutError, json.JSONDecodeError) as error:
                raise RuntimeError(f"OpenClaw gateway response failed: {error}") from error
            if not isinstance(msg, dict):
                raise RuntimeError("OpenClaw gateway response must be an object")
            if msg.get("type") == "event":
                continue
            if msg.get("id") != ident:
                continue
            if not msg.get("ok"):
                raise RuntimeError(f"OpenClaw {method} failed: {msg.get('error')}")
            return msg.get("payload", {})

    async def prompt(self, text: str, *, session_key: str | None = None) -> AsyncIterator[OpenClawEvent]:
        key = session_key or self.session_key
        accepted = await self.request("chat.send", {"sessionKey": key, "message": text, "deliver": False, "idempotencyKey": str(uuid.uuid4())})
        run_id = accepted.get("runId")
        if not isinstance(run_id, str):
            raise RuntimeError(f"OpenClaw chat.send returned no runId: {accepted!r}")
        wait_timeout_ms = 120000
        result = await self.request(
            "agent.wait",
            {"runId": run_id, "timeoutMs": wait_timeout_ms},
            response_timeout_seconds=max(self.timeout_seconds, wait_timeout_ms / 1000 + 5),
        )
        yield OpenClawEvent("agent.wait", result)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
