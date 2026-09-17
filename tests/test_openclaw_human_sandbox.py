import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from fusion_flow.agent_runtime import AgentInvocation
from fusion_flow.adapters.openclaw_cli import OpenClawCliRuntime


class _FakeProcess:
    returncode = 0

    async def communicate(self, _input):
        return b'{"ok":true,"status":"ok","final":"{}"}', b""


class OpenClawHumanSandboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_human_preparation_uses_exec_with_workspace_read_only_policy(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            workspace = root / "workspace"
            workspace.mkdir()
            ambient = root / "openclaw.json"
            ambient.write_text('{"tools":{"profile":"full","allow":["exec"]}}', encoding="utf-8")
            captured = {}

            async def fake_create(*args, **kwargs):
                captured["args"] = args
                captured["env"] = kwargs["env"]
                config_path = Path(args[args.index("--config") + 1])
                captured["config"] = json.loads(config_path.read_text(encoding="utf-8"))
                return _FakeProcess()

            runtime = OpenClawCliRuntime(
                command=("openclaw", "agent"),
                env={"OPENCLAW_CONFIG_PATH": str(ambient), "PATH": os.environ.get("PATH", "")},
            )
            invocation = AgentInvocation("prepare question", "human-review-123", workspace)
            with patch("fusion_flow.adapters.openclaw_cli.asyncio.create_subprocess_exec", side_effect=fake_create):
                reply = await runtime.run_agent(invocation)

            self.assertTrue(reply.ok)
            self.assertIn("exec", captured["args"])
            self.assertNotIn("--session-key", captured["args"])
            self.assertEqual(
                captured["config"]["tools"],
                {"profile": "coding", "allow": ["read"], "fs": {"workspaceOnly": True}},
            )
            self.assertEqual(captured["config"]["$include"], str(ambient.resolve()))
            self.assertIn(str(ambient.parent.resolve()), captured["env"]["OPENCLAW_INCLUDE_ROOTS"].split(os.pathsep))
            self.assertEqual(captured["args"][captured["args"].index("--cwd") + 1], str(workspace))

    async def test_regular_agent_step_keeps_session_runtime(self):
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            captured = {}

            async def fake_create(*args, **kwargs):
                captured["args"] = args
                return _FakeProcess()

            runtime = OpenClawCliRuntime(command=("openclaw", "agent"))
            invocation = AgentInvocation("do work", "run-flow-step-123", workspace)
            with patch("fusion_flow.adapters.openclaw_cli.asyncio.create_subprocess_exec", side_effect=fake_create):
                reply = await runtime.run_agent(invocation)

            self.assertTrue(reply.ok)
            self.assertIn("--session-key", captured["args"])
            self.assertNotIn("exec", captured["args"])


if __name__ == "__main__":
    unittest.main()
