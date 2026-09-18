import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime
from fusion_flow.agent_runtime import AgentReply
from fusion_flow.workflow_runner import ProgramInvocation


class _PreparingRuntime:
    def __init__(self, prepare):
        self.prepare = prepare
        self.prompts = []

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.prompts.append(invocation.prompt)
        self.prepare(invocation.workspace)
        return AgentReply(text=json.dumps({"runtime": sys.executable}))


class _InvalidRuntime:
    def __init__(self):
        self.calls = 0

    def supports_agent_steps(self):
        return True

    async def run_agent(self, _invocation):
        self.calls += 1
        return AgentReply(text="not-json")


class ProgramDispatchTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[1] / "src" / "run_flow.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_program_dispatch_has_no_direct_host_shortcuts(self):
        names = {
            node.name
            for node in self.tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        self.assertNotIn("_complete_program_step_openclaw", names)
        self.assertNotIn("_complete_program_step_hermes", names)

        node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_complete_program_step"
        )
        rendered = ast.unparse(node)
        self.assertIn("_complete_host_program_step", rendered)
        self.assertIn("compile_program", rendered)
        self.assertIn("execute_program", rendered)
        self.assertNotIn("sys.executable", rendered)

    async def test_program_agent_can_prepare_dependency_before_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            script = root / "program.py"
            script.write_text(
                "import prepared_dependency\nprint(prepared_dependency.VALUE)\n",
                encoding="utf-8",
            )

            def prepare(workspace):
                (workspace / "prepared_dependency.py").write_text(
                    'VALUE = "ready"\n',
                    encoding="utf-8",
                )

            host = _PreparingRuntime(prepare)
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                ),
                output_ids=("result",),
            )
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertEqual(result, {"result": f"ready{os.linesep}"})
        self.assertEqual(len(host.prompts), 1)
        contract_prompt = host.prompts[0]
        self.assertIn('"script_path"', contract_prompt)
        self.assertIn(str(script), contract_prompt)
        self.assertIn("install a missing interpreter or dependency", contract_prompt)

    async def test_invalid_program_agent_response_never_falls_back_to_direct_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            marker = root / "executed.txt"
            script = root / "program.py"
            script.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
                "print('unexpected')\n",
                encoding="utf-8",
            )
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                ),
                output_ids=("result",),
            )
            host = _InvalidRuntime()
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertFalse(marker.exists())
        self.assertEqual(host.calls, 2)
        diagnostic = result["result"]["$fusion_flow/program_error"]
        self.assertEqual(diagnostic["phase"], "agent")
        self.assertEqual(diagnostic["kind"], "invalid_runtime_selection")


if __name__ == "__main__":
    unittest.main()
