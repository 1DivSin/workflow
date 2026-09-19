from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fusion_flow import mcp_server
from fusion_flow.adapters.codex_app_server import CodexAppServerClient
from fusion_flow.adapters.hermes_acp import HermesACPClient
from fusion_flow.adapters.openclaw_gateway import OpenClawGatewayClient
from fusion_flow.providers import load_providers


class RuntimeErrorBoundaryTests(unittest.TestCase):
    def test_mcp_stdio_reports_bad_json_and_continues(self):
        stdin = io.StringIO(
            '{bad\n'
            '[]\n'
            '{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        )
        stdout = io.StringIO()
        with patch.object(mcp_server.sys, "stdin", stdin), patch.object(
            mcp_server.sys, "stdout", stdout
        ):
            asyncio.run(mcp_server.serve_stdio())

        responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["error"]["code"], -32600)

    def test_corrupt_provider_config_is_ignored(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "providers.json"
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(load_providers(path), {})


class AdapterStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_codex_executable_has_context(self):
        with self.assertRaisesRegex(RuntimeError, "Codex app-server could not start"):
            await CodexAppServerClient(("missing-codex-executable",)).start()

    async def test_missing_hermes_executable_has_context(self):
        with self.assertRaisesRegex(RuntimeError, "Hermes ACP could not start"):
            await HermesACPClient(("missing-hermes-executable",)).start()

    async def test_openclaw_agent_wait_uses_full_server_wait_window(self):
        client = OpenClawGatewayClient(timeout_seconds=30)
        client.request = AsyncMock(
            side_effect=[{"runId": "run-1"}, {"status": "ok"}]
        )

        events = [event async for event in client.prompt("test")]

        self.assertEqual(events[0].event, "agent.wait")
        wait_call = client.request.await_args_list[1]
        self.assertEqual(wait_call.args[0], "agent.wait")
        self.assertEqual(wait_call.kwargs["response_timeout_seconds"], 125.0)


if __name__ == "__main__":
    unittest.main()
