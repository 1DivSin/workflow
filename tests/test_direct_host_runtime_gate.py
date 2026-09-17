import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime
from fusion_flow import host_adapter


class DirectHostRuntimeGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_hermes_run_flow_passes_runtime_gate(self):
        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "hermes", "HERMES_EXECUTABLE": "hermes"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "flow_path must stay inside"):
                await runtime.run_flow("../outside.workflow")

    async def test_codex_run_flow_passes_same_runtime_gate(self):
        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "codex", "CODEX_EXECUTABLE": "codex"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "flow_path must stay inside"):
                await runtime.run_flow("../outside.workflow")

    async def test_hermes_resume_passes_runtime_gate(self):
        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "hermes", "HERMES_EXECUTABLE": "hermes"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "human_response_json must be valid JSON or non-empty plain text",
            ):
                await runtime.run_flow_resume("run", "request", "")

    def test_openclaw_ai_socket_behavior_is_unchanged(self):
        with patch.dict(
            os.environ,
            {"PSI_WORKFLOW_HOST": "openclaw", "OPENCLAW_EXECUTABLE": "openclaw"},
            clear=False,
        ):
            self.assertIsNone(host_adapter.ai_socket())
            self.assertIsNotNone(host_adapter.agent_runtime())

    def test_generic_host_still_has_no_direct_runtime_token(self):
        with patch.dict(os.environ, {"PSI_WORKFLOW_HOST": ""}, clear=False):
            self.assertIsNone(host_adapter.ai_socket())


if __name__ == "__main__":
    unittest.main()
