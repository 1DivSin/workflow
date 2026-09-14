from __future__ import annotations

import asyncio
import importlib.util
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_adapter_module():
    package = types.ModuleType("fusion_flow")
    package.__path__ = [str(ROOT / "src" / "fusion_flow")]
    sys.modules.setdefault("fusion_flow", package)
    adapters = types.ModuleType("fusion_flow.adapters")
    adapters.__path__ = [str(ROOT / "src" / "fusion_flow" / "adapters")]
    sys.modules.setdefault("fusion_flow.adapters", adapters)
    runtime = _load_module("fusion_flow.agent_runtime", ROOT / "src" / "fusion_flow" / "agent_runtime.py")
    adapter = _load_module(
        "fusion_flow.adapters.openclaw_cli",
        ROOT / "src" / "fusion_flow" / "adapters" / "openclaw_cli.py",
    )
    return runtime, adapter


class OpenClawCliRuntimeTests(unittest.TestCase):
    def test_invokes_host_cli_without_gateway_credentials_in_arguments(self) -> None:
        runtime_module, adapter_module = _load_adapter_module()
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "fake_openclaw.py"
            script.write_text(
                textwrap.dedent(
                    """
                    import json
                    import sys

                    print(json.dumps({
                        "ok": True,
                        "status": "ok",
                        "final": sys.stdin.read(),
                        "sessionId": next((sys.argv[i + 1] for i, value in enumerate(sys.argv[:-1]) if value == "--session-key"), None),
                    }))
                    """
                ),
                encoding="utf-8",
            )
            request = runtime_module.AgentRequest(
                prompt="Reply with PONG",
                session_id="run/step-1",
                workspace=Path(temp),
            )
            runtime = adapter_module.OpenClawCliRuntime(
                command=(sys.executable, str(script)),
            )
            command = runtime.command_for(request)
            self.assertNotIn("--token", command)
            self.assertNotIn("--password", command)
            result = asyncio.run(
                runtime.invoke(request)
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.text, "Reply with PONG")
        self.assertTrue(result.session_id.startswith("agent:main:workflow:"))

    def test_preserves_structured_cli_failure(self) -> None:
        runtime_module, adapter_module = _load_adapter_module()
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp) / "fake_openclaw.py"
            script.write_text(
                "import json; print(json.dumps({'ok': False, 'status': 'error', 'error': {'message': 'denied'}})); raise SystemExit(1)\n",
                encoding="utf-8",
            )
            request = runtime_module.AgentRequest(
                prompt="work",
                session_id="step-1",
                workspace=Path(temp),
            )
            result = asyncio.run(
                adapter_module.OpenClawCliRuntime(
                    command=(sys.executable, str(script)),
                ).invoke(request)
            )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error, "denied")


if __name__ == "__main__":
    unittest.main()
