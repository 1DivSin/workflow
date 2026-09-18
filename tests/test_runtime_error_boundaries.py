from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fusion_flow import mcp_server
from fusion_flow.adapters.codex_app_server import CodexAppServerClient
from fusion_flow.adapters.hermes_acp import HermesACPClient
from fusion_flow.providers import load_providers


class RuntimeErrorBoundaryTests(unittest.TestCase):
    def test_mcp_stdio_reports_bad_json_and_continues(self):
        stdin = io.StringIO("{bad\n[]\n{\\\"jsonrpc\\\":\\\"2.0\\\",\\\"method\\\":\\\"notifications/initialized\\\"}\n")
        stdout = io.StringIO()
        with patch.object(mcp_server.sys, "stdin", stdin), patch.object(mcp_server.sys, "stdout", stdout):
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


if __name__ == "__main__":
    unittest.main()
